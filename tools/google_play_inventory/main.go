// Command google-play-inventory records current Google Play metadata for APKs.
package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	googleplayscraper "github.com/kryuchenko/google-play-scraper"
)

var (
	playVersionPattern = regexp.MustCompile(`"141":\[\[\["((?:\\.|[^"\\])*)"\]\]`)
	playUpdatedPattern = regexp.MustCompile(`"146":\[\["(?:\\.|[^"\\])*",\[([0-9]+)`)
)

type config struct {
	input              string
	inputStatuses      string
	discoverDevelopers bool
	output             string
	packageID          string
	country            string
	fallbackCountries  string
	throttle           time.Duration
	timeout            time.Duration
}

type result struct {
	PackageID        string            `json:"package_id"`
	LookupDate       string            `json:"lookup_date"`
	Country          string            `json:"country"`
	Status           string            `json:"status"`
	Error            string            `json:"error,omitempty"`
	Availability     map[string]string `json:"availability,omitempty"`
	Title            string            `json:"title,omitempty"`
	Version          string            `json:"version,omitempty"`
	Released         string            `json:"released,omitempty"`
	Updated          string            `json:"updated,omitempty"`
	Developer        string            `json:"developer,omitempty"`
	DeveloperID      string            `json:"developer_id,omitempty"`
	DeveloperWebsite string            `json:"developer_website,omitempty"`
	AndroidVersion   string            `json:"android_version,omitempty"`
	Available        bool              `json:"available"`
	URL              string            `json:"url,omitempty"`
}

type developerApp struct {
	PackageID string `json:"package_id"`
	Title     string `json:"title"`
	URL       string `json:"url"`
}

type developerCatalog struct {
	Developer   string         `json:"developer"`
	DeveloperID string         `json:"developer_id"`
	QueryID     string         `json:"query_id"`
	Status      string         `json:"status"`
	Error       string         `json:"error,omitempty"`
	Apps        []developerApp `json:"apps"`
}

func main() {
	cfg := parseFlags()
	client := googleplayscraper.NewClient(
		googleplayscraper.WithThrottle(cfg.throttle),
		googleplayscraper.WithTimeout(cfg.timeout),
	)
	ctx := context.Background()
	if cfg.discoverDevelopers {
		catalogs, err := discoverDeveloperApps(ctx, client, cfg)
		if err != nil {
			fatal(err)
		}
		if err := writeJSON(cfg.output, catalogs); err != nil {
			fatal(err)
		}
		return
	}

	packageIDs, err := loadPackageIDs(cfg)
	if err != nil {
		fatal(err)
	}
	results := make([]result, 0, len(packageIDs))
	for index, packageID := range packageIDs {
		fmt.Fprintf(os.Stderr, "[%d/%d] %s\n", index+1, len(packageIDs), packageID)
		results = append(results, lookup(ctx, client, cfg, packageID))
	}

	if err := writeJSON(cfg.output, results); err != nil {
		fatal(err)
	}
}

func parseFlags() config {
	var cfg config
	flag.StringVar(&cfg.input, "input", "", "CSV containing a package_id column")
	flag.StringVar(&cfg.inputStatuses, "input-statuses", "", "comma-separated statuses to select from JSON input")
	flag.BoolVar(&cfg.discoverDevelopers, "discover-developers", false, "list apps from developers found in JSON input")
	flag.StringVar(&cfg.output, "output", "", "JSON output path (stdout when empty)")
	flag.StringVar(&cfg.packageID, "package", "", "single package ID instead of an input CSV")
	flag.StringVar(&cfg.country, "country", "us", "primary Google Play country")
	flag.StringVar(
		&cfg.fallbackCountries,
		"fallback-countries",
		"no,gb,de,ca,au,jp",
		"countries probed when the primary lookup is unavailable",
	)
	flag.DurationVar(&cfg.throttle, "throttle", 500*time.Millisecond, "minimum delay between Play requests")
	flag.DurationVar(&cfg.timeout, "timeout", 60*time.Second, "per-request timeout")
	flag.Parse()
	return cfg
}

func discoverDeveloperApps(
	ctx context.Context,
	client *googleplayscraper.Client,
	cfg config,
) ([]developerCatalog, error) {
	if cfg.input == "" {
		return nil, errors.New("developer discovery requires -input JSON")
	}
	file, err := os.Open(cfg.input)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var records []result
	if err := json.NewDecoder(file).Decode(&records); err != nil {
		return nil, fmt.Errorf("read developer input: %w", err)
	}

	developers := make(map[string]string)
	for _, record := range records {
		if record.DeveloperID != "" {
			developers[record.DeveloperID] = record.Developer
		}
	}
	developerIDs := make([]string, 0, len(developers))
	for developerID := range developers {
		developerIDs = append(developerIDs, developerID)
	}
	sort.Strings(developerIDs)

	catalogs := make([]developerCatalog, 0, len(developerIDs))
	for index, developerID := range developerIDs {
		queryID := normalizeDeveloperID(developerID)
		catalog := developerCatalog{
			Developer:   developers[developerID],
			DeveloperID: developerID,
			QueryID:     queryID,
			Status:      "available",
			Apps:        []developerApp{},
		}
		fmt.Fprintf(os.Stderr, "[%d/%d] %s\n", index+1, len(developerIDs), catalog.Developer)
		apps, err := client.Developer(ctx, googleplayscraper.DeveloperOptions{
			DevID:      queryID,
			Num:        250,
			Lang:       "en",
			Country:    cfg.country,
			FullDetail: false,
		})
		if err != nil {
			catalog.Status = "fetch_error"
			catalog.Error = err.Error()
			catalogs = append(catalogs, catalog)
			continue
		}
		for _, app := range apps {
			catalog.Apps = append(catalog.Apps, developerApp{
				PackageID: app.AppID,
				Title:     app.Title,
				URL:       app.URL,
			})
		}
		sort.Slice(catalog.Apps, func(left, right int) bool {
			return catalog.Apps[left].PackageID < catalog.Apps[right].PackageID
		})
		catalogs = append(catalogs, catalog)
	}
	return catalogs, nil
}

func normalizeDeveloperID(developerID string) string {
	parsed, err := url.Parse(developerID)
	if err == nil && parsed.Query().Get("id") != "" {
		return parsed.Query().Get("id")
	}
	return developerID
}

func loadPackageIDs(cfg config) ([]string, error) {
	if cfg.packageID != "" {
		return []string{cfg.packageID}, nil
	}
	if cfg.input == "" {
		return nil, errors.New("provide -package or -input")
	}
	if strings.HasSuffix(strings.ToLower(cfg.input), ".json") {
		return loadPackageIDsFromJSON(cfg.input, splitValues(cfg.inputStatuses))
	}

	file, err := os.Open(cfg.input)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	header, err := reader.Read()
	if err != nil {
		return nil, fmt.Errorf("read CSV header: %w", err)
	}
	packageColumn := -1
	for index, name := range header {
		if name == "package_id" {
			packageColumn = index
			break
		}
	}
	if packageColumn < 0 {
		return nil, errors.New("input CSV has no package_id column")
	}

	seen := make(map[string]bool)
	var packageIDs []string
	for {
		row, err := reader.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("read CSV: %w", err)
		}
		if packageColumn >= len(row) {
			continue
		}
		packageID := strings.TrimSpace(row[packageColumn])
		if packageID != "" && !seen[packageID] {
			seen[packageID] = true
			packageIDs = append(packageIDs, packageID)
		}
	}
	sort.Strings(packageIDs)
	return packageIDs, nil
}

func loadPackageIDsFromJSON(path string, statuses []string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var records []result
	if err := json.NewDecoder(file).Decode(&records); err != nil {
		return nil, fmt.Errorf("read JSON input: %w", err)
	}
	selected := make(map[string]bool, len(statuses))
	for _, status := range statuses {
		selected[status] = true
	}
	var packageIDs []string
	for _, record := range records {
		if record.PackageID == "" || len(selected) > 0 && !selected[record.Status] {
			continue
		}
		packageIDs = append(packageIDs, record.PackageID)
	}
	sort.Strings(packageIDs)
	return packageIDs, nil
}

func lookup(
	ctx context.Context,
	client *googleplayscraper.Client,
	cfg config,
	packageID string,
) result {
	record := result{
		PackageID:  packageID,
		LookupDate: time.Now().UTC().Format(time.DateOnly),
		Country:    strings.ToLower(cfg.country),
	}
	app, err := client.App(ctx, packageID, googleplayscraper.AppOptions{
		Lang:    "en",
		Country: cfg.country,
	})
	if err == nil {
		record.Title = app.Title
		record.Version = app.Version
		record.Released = epochDate(app.Released)
		record.Updated = epochDate(app.Updated)
		record.Developer = app.Developer
		record.DeveloperID = app.DeveloperID
		record.DeveloperWebsite = app.DeveloperWebsite
		record.AndroidVersion = app.AndroidVersion
		record.Available = app.Available
		record.URL = app.URL
		if app.Available {
			version, updated, metadataErr := fetchRawVersion(ctx, packageID, cfg.country)
			if record.Version == "" {
				record.Version = version
			}
			if record.Updated == "" {
				record.Updated = updated
			}
			if metadataErr != nil && (record.Version == "" || record.Updated == "") {
				record.Error = joinErrors(record.Error, "raw metadata: "+metadataErr.Error())
			}
			record.Status = "available"
			return record
		}
		record.Status = "not_in_region"
	} else {
		record.Error = err.Error()
	}

	countries := splitCountries(cfg.country + "," + cfg.fallbackCountries)
	availability, availabilityErr := client.Availability(
		ctx,
		packageID,
		googleplayscraper.AvailabilityOptions{
			Countries:   countries,
			Lang:        "en",
			Concurrency: 1,
		},
	)
	if availabilityErr != nil {
		record.Status = "fetch_error"
		record.Error = joinErrors(record.Error, availabilityErr.Error())
		return record
	}

	record.Availability = make(map[string]string, len(availability.Statuses))
	hasAvailable := false
	hasRegionListing := false
	hasFetchError := false
	for country, status := range availability.Statuses {
		record.Availability[country] = status.String()
		switch status {
		case googleplayscraper.StatusAvailable:
			hasAvailable = true
		case googleplayscraper.StatusNotInRegion:
			hasRegionListing = true
		case googleplayscraper.StatusFetchError:
			hasFetchError = true
		}
	}
	for country, availabilityErr := range availability.Errors {
		record.Error = joinErrors(record.Error, country+": "+availabilityErr.Error())
	}

	switch {
	case hasAvailable:
		record.Status = "region_restricted"
	case hasRegionListing:
		record.Status = "not_in_region"
	case hasFetchError:
		record.Status = "fetch_error"
	default:
		record.Status = "not_found"
	}
	return record
}

func fetchRawVersion(ctx context.Context, packageID, country string) (string, string, error) {
	storeURL := "https://play.google.com/store/apps/details?id=" + url.QueryEscape(packageID) +
		"&hl=en&gl=" + url.QueryEscape(country)
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, storeURL, nil)
	if err != nil {
		return "", "", err
	}
	request.Header.Set("User-Agent", "Mozilla/5.0 (compatible; ha-adjustable-bed APK inventory)")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return "", "", err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return "", "", fmt.Errorf("HTTP %s", response.Status)
	}
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return "", "", err
	}
	return parseRawVersion(body)
}

func parseRawVersion(body []byte) (string, string, error) {
	versionMatch := playVersionPattern.FindSubmatch(body)
	updatedMatch := playUpdatedPattern.FindSubmatch(body)
	if len(versionMatch) < 2 && len(updatedMatch) < 2 {
		return "", "", errors.New("version and update metadata were absent")
	}

	var version string
	if len(versionMatch) >= 2 {
		if err := json.Unmarshal(append(append([]byte{'"'}, versionMatch[1]...), '"'), &version); err != nil {
			return "", "", fmt.Errorf("decode version: %w", err)
		}
	}
	var updated string
	if len(updatedMatch) >= 2 {
		epoch, err := strconv.ParseInt(string(updatedMatch[1]), 10, 64)
		if err != nil {
			return "", "", fmt.Errorf("decode update timestamp: %w", err)
		}
		updated = epochDate(epoch)
	}
	return version, updated, nil
}

func splitCountries(value string) []string {
	return splitValues(value)
}

func splitValues(value string) []string {
	seen := make(map[string]bool)
	var countries []string
	for _, country := range strings.Split(value, ",") {
		country = strings.ToLower(strings.TrimSpace(country))
		if country != "" && !seen[country] {
			seen[country] = true
			countries = append(countries, country)
		}
	}
	return countries
}

func epochDate(epoch int64) string {
	if epoch == 0 {
		return ""
	}
	return time.Unix(epoch, 0).UTC().Format(time.DateOnly)
}

func joinErrors(left, right string) string {
	if left == "" {
		return right
	}
	if right == "" {
		return left
	}
	return left + "; " + right
}

func writeJSON(path string, value any) error {
	var writer io.Writer = os.Stdout
	if path != "" {
		file, err := os.Create(path)
		if err != nil {
			return err
		}
		defer file.Close()
		writer = file
	}
	encoder := json.NewEncoder(writer)
	encoder.SetIndent("", "  ")
	encoder.SetEscapeHTML(false)
	return encoder.Encode(value)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}

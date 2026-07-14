package main

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestParseRawVersion(t *testing.T) {
	body := []byte(`prefix "141":[[["21.3.7"]],[[[36]],[[[26,"8.0"]]]]],"146":[["May 23, 2026",[1779523338,489000000]]] suffix`)

	version, updated, err := parseRawVersion(body)
	if err != nil {
		t.Fatal(err)
	}
	if version != "21.3.7" {
		t.Fatalf("version = %q, want 21.3.7", version)
	}
	if updated != "2026-05-23" {
		t.Fatalf("updated = %q, want 2026-05-23", updated)
	}
}

func TestParseRawVersionMissing(t *testing.T) {
	_, _, err := parseRawVersion([]byte("no metadata here"))
	if err == nil {
		t.Fatal("expected missing metadata error")
	}
}

func TestLoadPackageIDsFromJSONFiltersStatuses(t *testing.T) {
	path := filepath.Join(t.TempDir(), "play.json")
	contents := `[
  {"package_id":"com.example.available","status":"available"},
  {"package_id":"com.example.missing","status":"not_found"},
  {"package_id":"com.example.restricted","status":"not_in_region"}
]`
	if err := os.WriteFile(path, []byte(contents), 0o600); err != nil {
		t.Fatal(err)
	}

	got, err := loadPackageIDsFromJSON(path, []string{"not_found", "not_in_region"})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"com.example.missing", "com.example.restricted"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("package IDs = %v, want %v", got, want)
	}
}

func TestNormalizeDeveloperID(t *testing.T) {
	if got := normalizeDeveloperID("/store/apps/dev?id=5815187403158685768"); got != "5815187403158685768" {
		t.Fatalf("developer ID = %q", got)
	}
}

"""Strict configuration for production tracker publication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .fanout import TrackerFormat, TrackerTarget
from .github_contents import GitHubContentsTarget

PUBLICATION_CONFIG_REVISION = "phase4-v2-tracker-publication-v1"
_MAX_TARGETS = 32


@dataclass(frozen=True, slots=True)
class TrackerPublicationConfig:
    """One exact repository, existing branch, and complete tracker target set."""

    repository: str
    branch: str
    targets: tuple[TrackerTarget, ...]

    def __post_init__(self) -> None:
        validated = GitHubContentsTarget(self.repository, self.branch, "tracker")
        if (validated.repository, validated.branch) != (self.repository, self.branch):
            raise ValueError("publication endpoint is not canonical")
        if (
            type(self.targets) is not tuple
            or not self.targets
            or len(self.targets) > _MAX_TARGETS
            or any(type(item) is not TrackerTarget for item in self.targets)
        ):
            raise ValueError("publication targets must be a non-empty bounded exact tuple")
        if self.targets != tuple(sorted(self.targets)):
            raise ValueError("publication targets must be sorted")
        if len({target.path for target in self.targets}) != len(self.targets):
            raise ValueError("publication target paths must be unique")

    def to_data(self) -> dict[str, object]:
        return {
            "schema_revision": PUBLICATION_CONFIG_REVISION,
            "repository": self.repository,
            "branch": self.branch,
            "targets": [
                {"path": target.path, "format": target.format.value} for target in self.targets
            ],
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_data(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def parse_publication_config(raw: object) -> TrackerPublicationConfig:
    """Parse a closed publication configuration without contacting GitHub."""

    if type(raw) is not dict or set(raw) != {
        "schema_revision",
        "repository",
        "branch",
        "targets",
    }:
        raise ValueError("publication config has unexpected fields")
    if raw["schema_revision"] != PUBLICATION_CONFIG_REVISION:
        raise ValueError("publication config revision is unsupported")
    repository = raw["repository"]
    branch = raw["branch"]
    if type(repository) is not str or type(branch) is not str:
        raise ValueError("publication repository and branch must be strings")
    validated = GitHubContentsTarget(repository, branch, "tracker")
    raw_targets = raw["targets"]
    if type(raw_targets) is not list or not raw_targets or len(raw_targets) > _MAX_TARGETS:
        raise ValueError("publication targets must be a non-empty bounded array")
    targets: list[TrackerTarget] = []
    for index, raw_target in enumerate(raw_targets):
        if type(raw_target) is not dict or set(raw_target) != {"path", "format"}:
            raise ValueError(f"publication target {index} has unexpected fields")
        path = raw_target["path"]
        format_value = raw_target["format"]
        if type(path) is not str or type(format_value) is not str:
            raise ValueError(f"publication target {index} fields must be strings")
        if path.endswith("/"):
            raise ValueError(f"publication target {index} path must identify a file")
        try:
            tracker_format = TrackerFormat(format_value)
        except ValueError as error:
            raise ValueError(f"publication target {index} format is unsupported") from error
        targets.append(TrackerTarget(path, tracker_format))
    canonical_targets = tuple(sorted(targets))
    if tuple(targets) != canonical_targets:
        raise ValueError("publication targets must be sorted")
    if len({target.path for target in canonical_targets}) != len(canonical_targets):
        raise ValueError("publication target paths must be unique")
    return TrackerPublicationConfig(
        repository=validated.repository,
        branch=validated.branch,
        targets=canonical_targets,
    )

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class SeriesFinding:
    case_id: str
    series_label: str
    relative_dir: str
    series_dir: str
    file_count: int
    readable_count: int
    unreadable_count: int
    parameter_values: dict[str, list[str]]
    batch_values: dict[str, str]
    varying_parameters: list[str]
    missing_critical_tags: list[str]
    issues: list[str]
    severity: str
    batch_signature: str
    batch_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CaseFinding:
    case_id: str
    series_count: int
    batch_ids: list[str]
    batch_count: int
    varying_fields: list[str]
    within_series_issues: list[str]
    series_dirs: list[str]
    severity: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class BatchFinding:
    batch_id: str
    batch_signature: str
    series_count: int
    case_count: int
    case_ids: list[str]
    series_labels: list[str]
    representative_values: dict[str, str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class AuditSummary:
    generated_at: str
    root: str
    total_candidate_files: int
    total_series_dirs: int
    total_cases: int
    total_batches: int
    batch_fields: list[str]
    critical_tags: list[str]
    series_severity_counts: dict[str, int]
    case_severity_counts: dict[str, int]
    issue_counts: dict[str, int]
    parameter_variation: dict[str, dict[str, object]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

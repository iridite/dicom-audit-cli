from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pydicom

from dicom_audit_cli.models import AuditSummary, BatchFinding, CaseFinding, SeriesFinding


DEFAULT_BATCH_TAGS = [
    "Modality",
    "Manufacturer",
    "ManufacturerModelName",
    "Rows",
    "Columns",
    "PixelSpacing",
    "SliceThickness",
    "ImageOrientationPatient",
    "ConvolutionKernel",
    "KVP",
]

DEFAULT_CRITICAL_TAGS = [
    "Modality",
    "Rows",
    "Columns",
    "PixelSpacing",
    "SliceThickness",
    "ImageOrientationPatient",
]

SEVERITY_ORDER = {"ok": 0, "warning": 1, "error": 2}


def normalize_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    return str(value)


def infer_case_id(relative_dir: Path, case_pattern: re.Pattern[str]) -> str:
    for part in relative_dir.parts:
        if case_pattern.fullmatch(part):
            return part
    if relative_dir.parts:
        return relative_dir.parts[0]
    return "unknown-case"


def infer_series_label(relative_dir: Path) -> str:
    if not relative_dir.parts:
        return "unknown-series"
    if len(relative_dir.parts) >= 2:
        return relative_dir.parts[-2]
    return relative_dir.parts[-1]


def should_skip(path: Path, excluded_names: set[str]) -> bool:
    return any(part.lower() in excluded_names for part in path.parts)


def normalize_suffixes(raw_values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in raw_values:
        suffix = value.strip().lower()
        if not suffix:
            continue
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix not in normalized:
            normalized.append(suffix)
    return normalized or [".dcm"]


def normalize_tag_list(raw_values: list[str], defaults: list[str]) -> list[str]:
    if not raw_values:
        return list(defaults)
    normalized: list[str] = []
    for item in raw_values:
        tag = item.strip()
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized or list(defaults)


def discover_series_files(
    root: Path,
    suffixes: list[str],
    excluded_names: set[str],
    all_files: bool,
) -> tuple[dict[Path, list[Path]], int]:
    grouped: dict[Path, list[Path]] = defaultdict(list)
    total_candidates = 0

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if should_skip(file_path.relative_to(root), excluded_names):
            continue
        if not all_files and file_path.suffix.lower() not in suffixes:
            continue
        grouped[file_path.parent].append(file_path)
        total_candidates += 1

    return grouped, total_candidates


def read_datasets(file_paths: list[Path]) -> tuple[list[pydicom.Dataset], int]:
    datasets: list[pydicom.Dataset] = []
    unreadable_count = 0
    for file_path in sorted(file_paths):
        try:
            ds = pydicom.dcmread(str(file_path), stop_before_pixels=True, force=True)
            datasets.append(ds)
        except Exception:
            unreadable_count += 1
    return datasets, unreadable_count


def severity_from_series_issues(issues: list[str], missing_critical_tags: list[str], readable_count: int) -> str:
    if readable_count == 0:
        return "error"
    if missing_critical_tags:
        return "warning"
    if issues:
        return "warning"
    return "ok"


def collect_parameter_values(datasets: list[pydicom.Dataset], tags: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for tag in tags:
        uniques = sorted(
            {
                normalize_value(getattr(ds, tag, None))
                for ds in datasets
                if getattr(ds, tag, None) is not None
            }
        )
        values[tag] = [value for value in uniques if value is not None]
    return values


def build_batch_values(parameter_values: dict[str, list[str]], batch_tags: list[str]) -> dict[str, str]:
    batch_values: dict[str, str] = {}
    for tag in batch_tags:
        values = parameter_values.get(tag, [])
        if not values:
            batch_values[tag] = "<missing>"
        elif len(values) == 1:
            batch_values[tag] = values[0]
        else:
            batch_values[tag] = "<varies>"
    return batch_values


def audit_series_dir(
    root: Path,
    series_dir: Path,
    file_paths: list[Path],
    case_pattern: re.Pattern[str],
    batch_tags: list[str],
    critical_tags: list[str],
    include_modality: str | None,
) -> SeriesFinding:
    relative_dir = series_dir.relative_to(root)
    case_id = infer_case_id(relative_dir, case_pattern)
    series_label = infer_series_label(relative_dir)
    datasets, unreadable_count = read_datasets(file_paths)
    file_count = len(file_paths)

    if not datasets:
        return SeriesFinding(
            case_id=case_id,
            series_label=series_label,
            relative_dir=str(relative_dir),
            series_dir=str(series_dir),
            file_count=file_count,
            readable_count=0,
            unreadable_count=unreadable_count,
            parameter_values={tag: [] for tag in sorted(set(batch_tags + critical_tags))},
            batch_values={tag: "<missing>" for tag in batch_tags},
            varying_parameters=[],
            missing_critical_tags=list(critical_tags),
            issues=["no_readable_dicom"],
            severity="error",
            batch_signature=json.dumps({tag: "<missing>" for tag in batch_tags}, ensure_ascii=False, sort_keys=True),
        )

    audit_tags = sorted(set(batch_tags + critical_tags))
    parameter_values = collect_parameter_values(datasets, audit_tags)
    varying_parameters = [tag for tag, values in parameter_values.items() if len(values) > 1]
    missing_critical_tags = [tag for tag in critical_tags if not parameter_values.get(tag)]
    issues: list[str] = []

    if unreadable_count:
        issues.append("unreadable_files_present")
    if varying_parameters:
        issues.append("within_series_parameter_variation")
    if missing_critical_tags:
        issues.append("critical_tags_missing")

    if include_modality:
        modality_values = parameter_values.get("Modality", [])
        if modality_values and any(value.upper() != include_modality.upper() for value in modality_values):
            issues.append("modality_mismatch")

    batch_values = build_batch_values(parameter_values, batch_tags)
    batch_signature = json.dumps(batch_values, ensure_ascii=False, sort_keys=True)
    severity = severity_from_series_issues(issues, missing_critical_tags, len(datasets))

    return SeriesFinding(
        case_id=case_id,
        series_label=series_label,
        relative_dir=str(relative_dir),
        series_dir=str(series_dir),
        file_count=file_count,
        readable_count=len(datasets),
        unreadable_count=unreadable_count,
        parameter_values=parameter_values,
        batch_values=batch_values,
        varying_parameters=varying_parameters,
        missing_critical_tags=missing_critical_tags,
        issues=issues,
        severity=severity,
        batch_signature=batch_signature,
    )


def assign_batches(series_findings: list[SeriesFinding], batch_tags: list[str]) -> list[BatchFinding]:
    grouped: dict[str, list[SeriesFinding]] = defaultdict(list)
    for item in series_findings:
        grouped[item.batch_signature].append(item)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), min(series.case_id for series in item[1]), item[0]),
    )

    batches: list[BatchFinding] = []
    for index, (signature, items) in enumerate(ordered_groups, start=1):
        batch_id = f"B{index:03d}"
        for item in items:
            item.batch_id = batch_id
        case_ids = sorted({item.case_id for item in items})
        series_labels = sorted({item.series_label for item in items})
        representative_values = {tag: items[0].batch_values[tag] for tag in batch_tags}
        batches.append(
            BatchFinding(
                batch_id=batch_id,
                batch_signature=signature,
                series_count=len(items),
                case_count=len(case_ids),
                case_ids=case_ids,
                series_labels=series_labels,
                representative_values=representative_values,
            )
        )

    return batches


def build_case_findings(series_findings: list[SeriesFinding], batch_tags: list[str]) -> list[CaseFinding]:
    grouped: dict[str, list[SeriesFinding]] = defaultdict(list)
    for item in series_findings:
        grouped[item.case_id].append(item)

    case_findings: list[CaseFinding] = []
    for case_id in sorted(grouped):
        items = sorted(grouped[case_id], key=lambda item: item.relative_dir)
        batch_ids = sorted({item.batch_id for item in items})
        varying_fields: list[str] = []
        for tag in batch_tags:
            values = {item.batch_values[tag] for item in items}
            if len(values) > 1:
                varying_fields.append(tag)

        within_series_issues = sorted({issue for item in items for issue in item.issues})
        severity = "ok"
        if any(item.severity == "error" for item in items):
            severity = "error"
        elif batch_ids and len(batch_ids) > 1 or varying_fields or within_series_issues:
            severity = "warning"

        case_findings.append(
            CaseFinding(
                case_id=case_id,
                series_count=len(items),
                batch_ids=batch_ids,
                batch_count=len(batch_ids),
                varying_fields=varying_fields,
                within_series_issues=within_series_issues,
                series_dirs=[item.relative_dir for item in items],
                severity=severity,
            )
        )

    return case_findings


def build_parameter_variation(series_findings: list[SeriesFinding], batch_tags: list[str]) -> dict[str, dict[str, object]]:
    variation: dict[str, dict[str, object]] = {}
    for tag in batch_tags:
        values = Counter(item.batch_values[tag] for item in series_findings)
        variation[tag] = {
            "distinct_value_count": len(values),
            "top_values": [
                {"value": value, "series_count": count}
                for value, count in values.most_common(10)
            ],
        }
    return variation


def build_summary(
    root: Path,
    total_candidate_files: int,
    batch_tags: list[str],
    critical_tags: list[str],
    series_findings: list[SeriesFinding],
    case_findings: list[CaseFinding],
    batches: list[BatchFinding],
) -> AuditSummary:
    series_severity_counts = Counter(item.severity for item in series_findings)
    case_severity_counts = Counter(item.severity for item in case_findings)
    issue_counts = Counter()
    for item in series_findings:
        issue_counts.update(item.issues)
    for item in case_findings:
        issue_counts.update(item.within_series_issues)
        if item.batch_count > 1:
            issue_counts["multiple_batches_within_case"] += 1
        for tag in item.varying_fields:
            issue_counts[f"case_field_variation:{tag}"] += 1

    return AuditSummary(
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        root=str(root),
        total_candidate_files=total_candidate_files,
        total_series_dirs=len(series_findings),
        total_cases=len(case_findings),
        total_batches=len(batches),
        batch_fields=batch_tags,
        critical_tags=critical_tags,
        series_severity_counts=dict(sorted(series_severity_counts.items())),
        case_severity_counts=dict(sorted(case_severity_counts.items())),
        issue_counts=dict(sorted(issue_counts.items())),
        parameter_variation=build_parameter_variation(series_findings, batch_tags),
    )


def scan_root(
    root: Path,
    suffixes: list[str],
    excluded_names: set[str],
    all_files: bool,
    case_regex: str,
    batch_tags: list[str],
    critical_tags: list[str],
    include_modality: str | None,
) -> tuple[AuditSummary, list[CaseFinding], list[BatchFinding], list[SeriesFinding]]:
    case_pattern = re.compile(case_regex)
    grouped_files, total_candidate_files = discover_series_files(
        root=root,
        suffixes=suffixes,
        excluded_names=excluded_names,
        all_files=all_files,
    )
    if not grouped_files:
        raise FileNotFoundError("No candidate DICOM files were found under the provided root path.")

    series_findings = [
        audit_series_dir(
            root=root,
            series_dir=series_dir,
            file_paths=file_paths,
            case_pattern=case_pattern,
            batch_tags=batch_tags,
            critical_tags=critical_tags,
            include_modality=include_modality,
        )
        for series_dir, file_paths in sorted(grouped_files.items(), key=lambda item: str(item[0]))
    ]
    series_findings.sort(key=lambda item: (item.case_id, item.relative_dir))

    batches = assign_batches(series_findings, batch_tags)
    case_findings = build_case_findings(series_findings, batch_tags)
    summary = build_summary(
        root=root,
        total_candidate_files=total_candidate_files,
        batch_tags=batch_tags,
        critical_tags=critical_tags,
        series_findings=series_findings,
        case_findings=case_findings,
        batches=batches,
    )
    return summary, case_findings, batches, series_findings

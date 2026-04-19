from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pydicom

from dicom_audit_cli.models import CaseFinding, SeriesFinding


REQUIRED_TAGS = {
    "Modality": "Modality",
    "Rows": "Rows",
    "Columns": "Columns",
    "PixelSpacing": "PixelSpacing",
    "SliceThickness": "SliceThickness",
    "ImagePositionPatient": "ImagePositionPatient",
    "ImageOrientationPatient": "ImageOrientationPatient",
    "RescaleIntercept": "RescaleIntercept",
    "RescaleSlope": "RescaleSlope",
    "StudyInstanceUID": "StudyInstanceUID",
    "SeriesInstanceUID": "SeriesInstanceUID",
    "SOPInstanceUID": "SOPInstanceUID",
}

DEFAULT_PHASE_ALIASES = {
    "ap": "arterial",
    "arterial": "arterial",
    "artery": "arterial",
    "art": "arterial",
    "pvp": "portal",
    "portal": "portal",
    "pv": "portal",
    "venous": "portal",
    "nc": "noncontrast",
    "noncontrast": "noncontrast",
    "non-contrast": "noncontrast",
    "plain": "noncontrast",
    "precontrast": "noncontrast",
    "pre-contrast": "noncontrast",
}

SEVERITY_ORDER = {"ok": 0, "warning": 1, "error": 2}
SERIES_ERROR_ISSUES = {
    "no_readable_dicom",
    "unexpected_modality",
    "required_tags_missing",
    "mixed_series_uid",
    "duplicate_sop_uid",
}
SERIES_WARNING_ISSUES = {
    "unreadable_files_present",
    "pixel_spacing_inconsistent",
    "slice_thickness_inconsistent",
    "orientation_inconsistent",
    "instance_number_duplicate_or_missing",
    "image_position_duplicate_or_missing",
    "series_description_empty",
    "unknown_phase",
}


def merge_phase_aliases(extra_aliases: list[str]) -> dict[str, str]:
    aliases = dict(DEFAULT_PHASE_ALIASES)
    for raw_item in extra_aliases:
        if "=" not in raw_item:
            raise ValueError(f"Invalid --phase-alias value: {raw_item}")
        alias, target = raw_item.split("=", 1)
        alias = alias.strip().lower()
        target = target.strip().lower()
        if not alias or not target:
            raise ValueError(f"Invalid --phase-alias value: {raw_item}")
        aliases[alias] = target
    return aliases


def normalize_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    return str(value)


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def simplify_series_description(text: str | None) -> str:
    if not text:
        return ""
    normalized = normalize_text(text)
    for token in ("contrast", "ce", "cplus", "cminus"):
        normalized = normalized.replace(token, "")
    return normalized


def infer_case_id(relative_dir: Path, case_pattern: re.Pattern[str]) -> str:
    for part in relative_dir.parts:
        if case_pattern.fullmatch(part):
            return part
    if relative_dir.parts:
        return relative_dir.parts[0]
    return "unknown-case"


def infer_phase(relative_dir: Path, series_description: str | None, aliases: dict[str, str]) -> tuple[str, str]:
    path_parts = [normalize_text(part) for part in relative_dir.parts]
    for token in reversed(path_parts):
        if token in aliases:
            return aliases[token], "path"

    if series_description:
        description_text = normalize_text(series_description)
        for alias, phase in aliases.items():
            if normalize_text(alias) and normalize_text(alias) in description_text:
                return phase, "series_description"

    return "unknown", "unknown"


def severity_from_issues(issues: list[str]) -> str:
    if any(issue in SERIES_ERROR_ISSUES for issue in issues):
        return "error"
    if issues:
        return "warning"
    return "ok"


def should_skip(path: Path, excluded_names: set[str]) -> bool:
    return any(part.lower() in excluded_names for part in path.parts)


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


def audit_series_dir(
    root: Path,
    series_dir: Path,
    file_paths: list[Path],
    aliases: dict[str, str],
    case_pattern: re.Pattern[str],
    required_modality: str | None,
) -> SeriesFinding:
    relative_dir = series_dir.relative_to(root)
    datasets, unreadable_count = read_datasets(file_paths)
    file_count = len(file_paths)
    issues: list[str] = []

    if not datasets:
        issues.append("no_readable_dicom")
        return SeriesFinding(
            case_id=infer_case_id(relative_dir, case_pattern),
            phase="unknown",
            phase_source="unknown",
            relative_dir=str(relative_dir),
            series_dir=str(series_dir),
            file_count=file_count,
            readable_count=0,
            unreadable_count=unreadable_count,
            modality=None,
            series_description=None,
            manufacturer=None,
            manufacturer_model_name=None,
            convolution_kernel=None,
            pixel_spacing_unique=[],
            slice_thickness_unique=[],
            orientation_unique=[],
            series_uid_unique_count=0,
            sop_uid_unique_count=0,
            instance_number_unique_count=0,
            image_position_unique_count=0,
            required_tag_missing=list(REQUIRED_TAGS),
            issues=issues,
            severity="error",
        )

    if unreadable_count:
        issues.append("unreadable_files_present")

    sample = datasets[0]
    required_tag_missing = [
        name
        for name, key in REQUIRED_TAGS.items()
        if any(getattr(ds, key, None) is None for ds in datasets)
    ]
    if required_tag_missing:
        issues.append("required_tags_missing")

    pixel_spacing_unique = sorted(
        {
            normalize_value(getattr(ds, "PixelSpacing", None))
            for ds in datasets
            if getattr(ds, "PixelSpacing", None) is not None
        }
    )
    slice_thickness_unique = sorted(
        {
            normalize_value(getattr(ds, "SliceThickness", None))
            for ds in datasets
            if getattr(ds, "SliceThickness", None) is not None
        }
    )
    orientation_unique = sorted(
        {
            normalize_value(getattr(ds, "ImageOrientationPatient", None))
            for ds in datasets
            if getattr(ds, "ImageOrientationPatient", None) is not None
        }
    )
    series_uids = {
        normalize_value(getattr(ds, "SeriesInstanceUID", None))
        for ds in datasets
        if getattr(ds, "SeriesInstanceUID", None) is not None
    }
    sop_uids = [
        normalize_value(getattr(ds, "SOPInstanceUID", None))
        for ds in datasets
        if getattr(ds, "SOPInstanceUID", None) is not None
    ]
    instance_numbers = [
        normalize_value(getattr(ds, "InstanceNumber", None))
        for ds in datasets
        if getattr(ds, "InstanceNumber", None) is not None
    ]
    image_positions = [
        normalize_value(getattr(ds, "ImagePositionPatient", None))
        for ds in datasets
        if getattr(ds, "ImagePositionPatient", None) is not None
    ]

    if len(pixel_spacing_unique) > 1:
        issues.append("pixel_spacing_inconsistent")
    if len(slice_thickness_unique) > 1:
        issues.append("slice_thickness_inconsistent")
    if len(orientation_unique) > 1:
        issues.append("orientation_inconsistent")
    if len(series_uids) > 1:
        issues.append("mixed_series_uid")
    if len(set(sop_uids)) != len(sop_uids):
        issues.append("duplicate_sop_uid")
    if instance_numbers and len(set(instance_numbers)) != len(datasets):
        issues.append("instance_number_duplicate_or_missing")
    if image_positions and len(set(image_positions)) != len(datasets):
        issues.append("image_position_duplicate_or_missing")

    modality = normalize_value(getattr(sample, "Modality", None))
    if required_modality and modality and modality.upper() != required_modality.upper():
        issues.append("unexpected_modality")

    series_description = normalize_value(getattr(sample, "SeriesDescription", None))
    if not series_description:
        issues.append("series_description_empty")

    phase, phase_source = infer_phase(relative_dir, series_description, aliases)
    if phase == "unknown":
        issues.append("unknown_phase")

    return SeriesFinding(
        case_id=infer_case_id(relative_dir, case_pattern),
        phase=phase,
        phase_source=phase_source,
        relative_dir=str(relative_dir),
        series_dir=str(series_dir),
        file_count=file_count,
        readable_count=len(datasets),
        unreadable_count=unreadable_count,
        modality=modality,
        series_description=series_description,
        manufacturer=normalize_value(getattr(sample, "Manufacturer", None)),
        manufacturer_model_name=normalize_value(getattr(sample, "ManufacturerModelName", None)),
        convolution_kernel=normalize_value(getattr(sample, "ConvolutionKernel", None)),
        pixel_spacing_unique=[value for value in pixel_spacing_unique if value is not None],
        slice_thickness_unique=[value for value in slice_thickness_unique if value is not None],
        orientation_unique=[value for value in orientation_unique if value is not None],
        series_uid_unique_count=len(series_uids),
        sop_uid_unique_count=len(set(sop_uids)),
        instance_number_unique_count=len(set(instance_numbers)),
        image_position_unique_count=len(set(image_positions)),
        required_tag_missing=required_tag_missing,
        issues=issues,
        severity=severity_from_issues(issues),
    )


def build_case_findings(
    series_findings: list[SeriesFinding],
    expected_phases: list[str],
) -> list[CaseFinding]:
    grouped: dict[str, list[SeriesFinding]] = defaultdict(list)
    for series in series_findings:
        grouped[series.case_id].append(series)

    case_findings: list[CaseFinding] = []
    for case_id in sorted(grouped):
        series_list = grouped[case_id]
        recognized_phase_map: dict[str, list[SeriesFinding]] = defaultdict(list)
        unknown_phase_series: list[str] = []
        issues: list[str] = []
        series_issue_summary = sorted({issue for series in series_list for issue in series.issues})
        severity = "ok"

        for series in series_list:
            severity = max(severity, series.severity, key=SEVERITY_ORDER.get)
            if series.phase == "unknown":
                unknown_phase_series.append(series.relative_dir)
            else:
                recognized_phase_map[series.phase].append(series)

        missing_phases = [phase for phase in expected_phases if phase not in recognized_phase_map]
        if missing_phases:
            issues.append(f"missing_expected_phases:{','.join(missing_phases)}")
            severity = "error"

        duplicate_phase_map = {
            phase: [item.relative_dir for item in items]
            for phase, items in recognized_phase_map.items()
            if len(items) > 1
        }
        if duplicate_phase_map:
            issues.append("duplicate_phase_series")
            severity = max(severity, "warning", key=SEVERITY_ORDER.get)

        if unknown_phase_series:
            issues.append("unknown_phase_series_present")
            severity = max(severity, "warning", key=SEVERITY_ORDER.get)

        cross_phase_series = {
            phase: items[0]
            for phase, items in recognized_phase_map.items()
            if len(items) == 1
        }
        comparable_series = [
            cross_phase_series[phase]
            for phase in expected_phases
            if phase in cross_phase_series
        ]
        if len(comparable_series) >= 2:
            thickness_values = {
                tuple(item.slice_thickness_unique)
                for item in comparable_series
                if item.slice_thickness_unique
            }
            spacing_values = {
                tuple(item.pixel_spacing_unique)
                for item in comparable_series
                if item.pixel_spacing_unique
            }
            description_values = {
                simplify_series_description(item.series_description)
                for item in comparable_series
            }
            if len(thickness_values) > 1:
                issues.append("cross_phase_slice_thickness_inconsistent")
                severity = max(severity, "warning", key=SEVERITY_ORDER.get)
            if len(spacing_values) > 1:
                issues.append("cross_phase_pixel_spacing_inconsistent")
                severity = max(severity, "warning", key=SEVERITY_ORDER.get)
            if len(description_values) > 1:
                issues.append("cross_phase_series_description_mismatch")
                severity = max(severity, "warning", key=SEVERITY_ORDER.get)

        case_findings.append(
            CaseFinding(
                case_id=case_id,
                recognized_phases=sorted(recognized_phase_map),
                missing_phases=missing_phases,
                unknown_phase_series=sorted(unknown_phase_series),
                duplicate_phase_map=duplicate_phase_map,
                series_issue_summary=series_issue_summary,
                issues=issues,
                severity=severity,
            )
        )

    return case_findings


def build_summary(
    root: Path,
    total_candidate_files: int,
    series_findings: list[SeriesFinding],
    case_findings: list[CaseFinding],
    expected_phases: list[str],
    aliases: dict[str, str],
) -> dict:
    severity_counter = Counter(series.severity for series in series_findings)
    case_severity_counter = Counter(case.severity for case in case_findings)
    issue_counter = Counter()
    for series in series_findings:
        issue_counter.update(series.issues)
    for case in case_findings:
        issue_counter.update(case.issues)

    complete_cases = sum(1 for case in case_findings if not case.missing_phases)
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": str(root),
        "expected_phases": expected_phases,
        "phase_aliases": aliases,
        "total_candidate_files": total_candidate_files,
        "total_series_dirs": len(series_findings),
        "total_cases": len(case_findings),
        "complete_cases": complete_cases,
        "series_severity_counts": dict(sorted(severity_counter.items())),
        "case_severity_counts": dict(sorted(case_severity_counter.items())),
        "issue_counts": dict(sorted(issue_counter.items())),
    }


def scan_root(
    root: Path,
    expected_phases: list[str],
    aliases: dict[str, str],
    suffixes: list[str],
    excluded_names: set[str],
    all_files: bool,
    case_regex: str,
    required_modality: str | None,
) -> tuple[dict, list[CaseFinding], list[SeriesFinding]]:
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
            aliases=aliases,
            case_pattern=case_pattern,
            required_modality=required_modality,
        )
        for series_dir, file_paths in sorted(grouped_files.items(), key=lambda item: str(item[0]))
    ]
    series_findings.sort(key=lambda item: (item.case_id, item.phase, item.relative_dir))

    case_findings = build_case_findings(series_findings, expected_phases)
    summary = build_summary(
        root=root,
        total_candidate_files=total_candidate_files,
        series_findings=series_findings,
        case_findings=case_findings,
        expected_phases=expected_phases,
        aliases=aliases,
    )
    return summary, case_findings, series_findings

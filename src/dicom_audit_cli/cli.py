from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dicom_audit_cli.audit import merge_phase_aliases, scan_root
from dicom_audit_cli.reporting import (
    build_payload,
    write_json_report,
    write_markdown_report,
    write_pdf_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recursively scan a DICOM root directory and emit JSON, Markdown, and PDF audit reports."
    )
    parser.add_argument("--root", required=True, help="Root folder to scan recursively.")
    parser.add_argument(
        "--output-dir",
        help="Directory for generated reports. Defaults to ./output/dicom_audit_<timestamp>.",
    )
    parser.add_argument(
        "--title",
        default="DICOM 技术完整性审计报告",
        help="Report title.",
    )
    parser.add_argument(
        "--modality",
        default="CT",
        help="Expected modality. Defaults to CT.",
    )
    parser.add_argument(
        "--expected-phases",
        default="arterial,portal,noncontrast",
        help="Comma-separated expected phases.",
    )
    parser.add_argument(
        "--phase-alias",
        action="append",
        default=[],
        help="Additional phase alias mapping, e.g. AP=arterial.",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to skip during recursive scanning. Repeatable.",
    )
    parser.add_argument(
        "--suffix",
        action="append",
        default=[".dcm"],
        help="Candidate file suffix. Repeatable. Defaults to .dcm.",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Attempt to read every file under root instead of filtering by suffix.",
    )
    parser.add_argument(
        "--case-regex",
        default=r"^\d+$",
        help="Regex used to infer case_id from path segments. Defaults to ^\\d+$.",
    )
    return parser


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


def ensure_output_dir(raw_output_dir: str | None) -> Path:
    if raw_output_dir:
        output_dir = Path(raw_output_dir).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = (Path.cwd() / "output" / f"dicom_audit_{stamp}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        parser.error(f"--root does not point to an existing directory: {root}")

    output_dir = ensure_output_dir(args.output_dir)
    expected_phases = [item.strip().lower() for item in args.expected_phases.split(",") if item.strip()]
    aliases = merge_phase_aliases(args.phase_alias)
    excluded_names = {item.strip().lower() for item in args.exclude_dir if item.strip()}
    suffixes = normalize_suffixes(args.suffix)

    summary, case_findings, series_findings = scan_root(
        root=root,
        expected_phases=expected_phases,
        aliases=aliases,
        suffixes=suffixes,
        excluded_names=excluded_names,
        all_files=args.all_files,
        case_regex=args.case_regex,
        required_modality=args.modality,
    )
    payload = build_payload(
        title=args.title,
        summary=summary,
        cases=[item.to_dict() for item in case_findings],
        series=[item.to_dict() for item in series_findings],
    )

    json_path = output_dir / "dicom_audit_report.json"
    md_path = output_dir / "dicom_audit_report.md"
    pdf_path = output_dir / "dicom_audit_report.pdf"

    write_json_report(json_path, payload)
    write_markdown_report(md_path, payload)
    write_pdf_report(pdf_path, payload)

    print(f"root={root}")
    print(f"total_candidate_files={summary['total_candidate_files']}")
    print(f"total_series_dirs={summary['total_series_dirs']}")
    print(f"total_cases={summary['total_cases']}")
    print(f"complete_cases={summary['complete_cases']}")
    print(f"json_report={json_path}")
    print(f"markdown_report={md_path}")
    print(f"pdf_report={pdf_path}")
    return 0

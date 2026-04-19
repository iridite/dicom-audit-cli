from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from dicom_audit_cli.audit import (
    DEFAULT_BATCH_TAGS,
    DEFAULT_CRITICAL_TAGS,
    normalize_suffixes,
    normalize_tag_list,
    scan_root,
)
from dicom_audit_cli.reporting import (
    build_payload,
    compile_typst_pdf,
    find_typst_binary,
    write_json_report,
    write_markdown_report,
    write_typst_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recursively scan a DICOM root directory and generate parameter-consistency reports."
    )
    parser.add_argument("--root", required=True, help="Root folder to scan recursively.")
    parser.add_argument(
        "--output-dir",
        help="Directory for generated reports. Defaults to ./output/dicom_audit_<timestamp>.",
    )
    parser.add_argument(
        "--title",
        default="DICOM 参数一致性审计报告",
        help="Report title.",
    )
    parser.add_argument(
        "--typst-binary",
        help="Optional path to typst executable. If omitted, the tool searches PATH and the current executable directory.",
    )
    parser.add_argument(
        "--modality",
        default="",
        help="Optional modality filter, e.g. CT. Default is no modality filter.",
    )
    parser.add_argument(
        "--batch-field",
        action="append",
        default=[],
        help="DICOM tag used to define parameter batches. Repeatable.",
    )
    parser.add_argument(
        "--critical-tag",
        action="append",
        default=[],
        help="DICOM tag that should exist for reliable parameter checking. Repeatable.",
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


def ensure_output_dir(raw_output_dir: str | None) -> Path:
    if raw_output_dir:
        output_dir = Path(raw_output_dir).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = (Path.cwd() / "output").resolve()
        output_dir = base_dir / stamp
        counter = 1
        while output_dir.exists():
            output_dir = base_dir / f"{stamp}_{counter:02d}"
            counter += 1
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        parser.error(f"--root does not point to an existing directory: {root}")

    output_dir = ensure_output_dir(args.output_dir)
    suffixes = normalize_suffixes(args.suffix)
    excluded_names = {item.strip().lower() for item in args.exclude_dir if item.strip()}
    batch_tags = normalize_tag_list(args.batch_field, DEFAULT_BATCH_TAGS)
    critical_tags = normalize_tag_list(args.critical_tag, DEFAULT_CRITICAL_TAGS)
    include_modality = args.modality.strip() or None

    summary, case_findings, batch_findings, series_findings = scan_root(
        root=root,
        suffixes=suffixes,
        excluded_names=excluded_names,
        all_files=args.all_files,
        case_regex=args.case_regex,
        batch_tags=batch_tags,
        critical_tags=critical_tags,
        include_modality=include_modality,
    )

    payload = build_payload(
        title=args.title,
        summary=summary.to_dict(),
        cases=[item.to_dict() for item in case_findings],
        batches=[item.to_dict() for item in batch_findings],
        series=[item.to_dict() for item in series_findings],
    )

    json_path = output_dir / "dicom_audit_report.json"
    md_path = output_dir / "dicom_audit_report.md"
    typ_path = output_dir / "dicom_audit_report.typ"
    pdf_path = output_dir / "dicom_audit_report.pdf"

    write_json_report(json_path, payload)
    write_markdown_report(md_path, payload)
    write_typst_report(typ_path, json_path)

    typst_binary = find_typst_binary(args.typst_binary)
    pdf_status = "skipped (typst not found)"
    if typst_binary:
        compile_typst_pdf(typst_binary, typ_path, pdf_path)
        pdf_status = str(pdf_path)

    print(f"root={root}")
    print(f"total_candidate_files={summary.total_candidate_files}")
    print(f"total_series_dirs={summary.total_series_dirs}")
    print(f"total_cases={summary.total_cases}")
    print(f"total_batches={summary.total_batches}")
    print(f"json_report={json_path}")
    print(f"markdown_report={md_path}")
    print(f"typst_report={typ_path}")
    print(f"pdf_report={pdf_status}")
    return 0

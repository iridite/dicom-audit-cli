from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def severity_label(value: str) -> str:
    mapping = {"ok": "正常", "warning": "警告", "error": "错误"}
    return mapping.get(value, value)


def format_issue_list(issues: list[str]) -> str:
    if not issues:
        return "无"
    return ", ".join(issues)


def format_case_issue_list(case: dict) -> str:
    issue_parts: list[str] = []
    if case["issues"]:
        issue_parts.append(", ".join(case["issues"]))
    if case.get("series_issue_summary"):
        issue_parts.append(f"series: {', '.join(case['series_issue_summary'])}")
    return " | ".join(issue_parts) if issue_parts else "无"


def format_case_phases(case: dict) -> str:
    return ", ".join(case["recognized_phases"]) if case["recognized_phases"] else "无"


def build_payload(title: str, summary: dict, cases: list[dict], series: list[dict]) -> dict:
    return {
        "title": title,
        "summary": summary,
        "cases": cases,
        "series": series,
    }


def write_json_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_markdown_report(payload: dict) -> str:
    title = payload["title"]
    summary = payload["summary"]
    cases = payload["cases"]
    series = payload["series"]

    lines = [
        f"# {title}",
        "",
        "## 摘要",
        f"- 生成时间：`{summary['generated_at']}`",
        f"- 扫描根目录：`{summary['root']}`",
        f"- 候选 DICOM 文件数：`{summary['total_candidate_files']}`",
        f"- series 目录数：`{summary['total_series_dirs']}`",
        f"- 病例数：`{summary['total_cases']}`",
        f"- 期相完整病例数：`{summary['complete_cases']}`",
        f"- 期望期相：`{', '.join(summary['expected_phases'])}`",
        "",
        "## 严重度统计",
        "",
        "| 维度 | 正常 | 警告 | 错误 |",
        "| --- | --- | --- | --- |",
        (
            f"| series | {summary['series_severity_counts'].get('ok', 0)} | "
            f"{summary['series_severity_counts'].get('warning', 0)} | "
            f"{summary['series_severity_counts'].get('error', 0)} |"
        ),
        (
            f"| case | {summary['case_severity_counts'].get('ok', 0)} | "
            f"{summary['case_severity_counts'].get('warning', 0)} | "
            f"{summary['case_severity_counts'].get('error', 0)} |"
        ),
        "",
        "## 病例概览",
        "",
        "| case_id | 状态 | 已识别期相 | 缺失期相 | 问题 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for case in cases:
        lines.append(
            f"| {case['case_id']} | {severity_label(case['severity'])} | "
            f"{format_case_phases(case)} | "
            f"{', '.join(case['missing_phases']) if case['missing_phases'] else '无'} | "
            f"{format_case_issue_list(case)} |"
        )

    lines.extend(
        [
            "",
            "## Series 详细结果",
            "",
            "| case_id | phase | 路径 | 文件数 | 可读数 | 状态 | 问题 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in series:
        lines.append(
            f"| {item['case_id']} | {item['phase']} | `{item['relative_dir']}` | "
            f"{item['file_count']} | {item['readable_count']} | {severity_label(item['severity'])} | "
            f"{format_issue_list(item['issues'])} |"
        )

    return "\n".join(lines) + "\n"


def write_markdown_report(path: Path, payload: dict) -> None:
    path.write_text(render_markdown_report(payload), encoding="utf-8")


def _register_chinese_font() -> str:
    font_name = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AuditTitle",
            parent=sample["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "AuditHeading1",
            parent=sample["Heading1"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "AuditBody",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1f2937"),
        ),
        "small": ParagraphStyle(
            "AuditSmall",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#334155"),
        ),
    }


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def write_pdf_report(path: Path, payload: dict) -> None:
    font_name = _register_chinese_font()
    styles = _styles(font_name)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=payload["title"],
    )

    summary = payload["summary"]
    cases = payload["cases"]
    series = payload["series"]
    story = [
        Paragraph(payload["title"], styles["title"]),
        Paragraph(f"生成时间：{summary['generated_at']}", styles["body"]),
        Paragraph(f"扫描根目录：{summary['root']}", styles["body"]),
        Spacer(1, 6),
        Paragraph("摘要", styles["h1"]),
    ]

    summary_rows = [
        ["项目", "值"],
        ["候选 DICOM 文件数", str(summary["total_candidate_files"])],
        ["series 目录数", str(summary["total_series_dirs"])],
        ["病例数", str(summary["total_cases"])],
        ["期相完整病例数", str(summary["complete_cases"])],
        ["期望期相", ", ".join(summary["expected_phases"])],
    ]
    summary_table = LongTable(summary_rows, colWidths=[42 * mm, 132 * mm], repeatRows=1)
    summary_table.setStyle(_table_style())
    story.extend([summary_table, Spacer(1, 8), Paragraph("病例概览", styles["h1"])])

    case_rows = [["case_id", "状态", "已识别期相", "缺失期相", "问题"]]
    for case in cases:
        case_rows.append(
            [
                case["case_id"],
                severity_label(case["severity"]),
                format_case_phases(case),
                ", ".join(case["missing_phases"]) if case["missing_phases"] else "无",
                format_case_issue_list(case),
            ]
        )
    case_table = LongTable(
        case_rows,
        colWidths=[20 * mm, 16 * mm, 40 * mm, 32 * mm, 72 * mm],
        repeatRows=1,
    )
    case_table.setStyle(_table_style())
    story.extend([case_table, PageBreak(), Paragraph("Series 详细结果", styles["h1"])])

    series_rows = [["case_id", "phase", "路径", "文件数", "可读数", "状态", "问题"]]
    for item in series:
        series_rows.append(
            [
                item["case_id"],
                item["phase"],
                item["relative_dir"],
                str(item["file_count"]),
                str(item["readable_count"]),
                severity_label(item["severity"]),
                format_issue_list(item["issues"]),
            ]
        )
    series_table = LongTable(
        series_rows,
        colWidths=[16 * mm, 20 * mm, 62 * mm, 14 * mm, 14 * mm, 16 * mm, 48 * mm],
        repeatRows=1,
    )
    series_table.setStyle(_table_style())
    story.append(series_table)

    if series:
        story.extend([PageBreak(), Paragraph("逐例详细说明", styles["h1"])])
        for item in series:
            details = [
                f"<b>case_id：</b>{item['case_id']}",
                f"<b>phase：</b>{item['phase']} ({item['phase_source']})",
                f"<b>路径：</b>{item['relative_dir']}",
                f"<b>状态：</b>{severity_label(item['severity'])}",
                f"<b>文件数 / 可读数：</b>{item['file_count']} / {item['readable_count']}",
                f"<b>SeriesDescription：</b>{item['series_description'] or '无'}",
                f"<b>ManufacturerModelName：</b>{item['manufacturer_model_name'] or '无'}",
                f"<b>ConvolutionKernel：</b>{item['convolution_kernel'] or '无'}",
                f"<b>PixelSpacing：</b>{', '.join(item['pixel_spacing_unique']) or '无'}",
                f"<b>SliceThickness：</b>{', '.join(item['slice_thickness_unique']) or '无'}",
                f"<b>问题：</b>{format_issue_list(item['issues'])}",
            ]
            story.append(Paragraph(" / ".join(details), styles["small"]))
            story.append(Spacer(1, 4))

    doc.build(story)

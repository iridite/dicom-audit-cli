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


def format_mapping(values: dict[str, str]) -> str:
    if not values:
        return "无"
    return "; ".join(f"{key}={value}" for key, value in values.items())


def build_payload(
    title: str,
    summary: dict,
    cases: list[dict],
    batches: list[dict],
    series: list[dict],
) -> dict:
    return {
        "title": title,
        "summary": summary,
        "cases": cases,
        "batches": batches,
        "series": series,
    }


def write_json_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_markdown_report(payload: dict) -> str:
    title = payload["title"]
    summary = payload["summary"]
    cases = payload["cases"]
    batches = payload["batches"]
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
        f"- 参数批次数：`{summary['total_batches']}`",
        f"- 用于分批的参数字段：`{', '.join(summary['batch_fields'])}`",
        f"- 关键检查字段：`{', '.join(summary['critical_tags'])}`",
        "- 批次划分规则：`仅按参数签名分组，不使用病例号、目录名或期相名`",
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
        "## 全局参数波动",
        "",
        "| 参数字段 | 不同取值数 | 主要取值（前 5 个） |",
        "| --- | --- | --- |",
    ]

    for tag, data in summary["parameter_variation"].items():
        top_values = ", ".join(
            f"{item['value']} ({item['series_count']})"
            for item in data["top_values"][:5]
        )
        lines.append(f"| {tag} | {data['distinct_value_count']} | {top_values or '无'} |")

    lines.extend(
        [
            "",
            "## 批次概览",
            "",
            "| batch_id | series 数 | case 数 | 代表参数 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for batch in batches:
        lines.append(
            f"| {batch['batch_id']} | {batch['series_count']} | {batch['case_count']} | "
            f"{format_mapping(batch['representative_values'])} |"
        )

    lines.extend(
        [
            "",
            "## 病例概览",
            "",
            "| case_id | series 数 | 批次数 | batch_ids | 波动字段 | 问题 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in cases:
        lines.append(
            f"| {case['case_id']} | {case['series_count']} | {case['batch_count']} | "
            f"{', '.join(case['batch_ids']) or '无'} | "
            f"{', '.join(case['varying_fields']) or '无'} | "
            f"{format_issue_list(case['within_series_issues'])} |"
        )

    lines.extend(
        [
            "",
            "## Series 详细结果",
            "",
            "| case_id | batch_id | 路径 | 文件数 | 可读数 | series 内波动字段 | 分批参数 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in series:
        lines.append(
            f"| {item['case_id']} | {item['batch_id']} | `{item['relative_dir']}` | "
            f"{item['file_count']} | {item['readable_count']} | "
            f"{', '.join(item['varying_parameters']) or '无'} | "
            f"{format_mapping(item['batch_values'])} |"
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
    batches = payload["batches"]
    series = payload["series"]
    story = [
        Paragraph(payload["title"], styles["title"]),
        Paragraph(f"生成时间：{summary['generated_at']}", styles["body"]),
        Paragraph(f"扫描根目录：{summary['root']}", styles["body"]),
        Paragraph("批次划分规则：仅按参数签名分组，不使用病例号、目录名或期相名。", styles["body"]),
        Spacer(1, 6),
        Paragraph("摘要", styles["h1"]),
    ]

    summary_rows = [
        ["项目", "值"],
        ["候选 DICOM 文件数", str(summary["total_candidate_files"])],
        ["series 目录数", str(summary["total_series_dirs"])],
        ["病例数", str(summary["total_cases"])],
        ["参数批次数", str(summary["total_batches"])],
        ["分批参数字段", ", ".join(summary["batch_fields"])],
        ["关键检查字段", ", ".join(summary["critical_tags"])],
    ]
    summary_table = LongTable(summary_rows, colWidths=[42 * mm, 132 * mm], repeatRows=1)
    summary_table.setStyle(_table_style())
    story.extend([summary_table, Spacer(1, 8), Paragraph("全局参数波动", styles["h1"])])

    variation_rows = [["参数字段", "不同取值数", "主要取值（前 5 个）"]]
    for tag, data in summary["parameter_variation"].items():
        top_values = ", ".join(
            f"{item['value']} ({item['series_count']})"
            for item in data["top_values"][:5]
        )
        variation_rows.append([tag, str(data["distinct_value_count"]), top_values or "无"])
    variation_table = LongTable(
        variation_rows,
        colWidths=[42 * mm, 22 * mm, 110 * mm],
        repeatRows=1,
    )
    variation_table.setStyle(_table_style())
    story.extend([variation_table, Spacer(1, 8), Paragraph("批次概览", styles["h1"])])

    batch_rows = [["batch_id", "series 数", "case 数", "代表参数"]]
    for batch in batches:
        batch_rows.append(
            [
                batch["batch_id"],
                str(batch["series_count"]),
                str(batch["case_count"]),
                format_mapping(batch["representative_values"]),
            ]
        )
    batch_table = LongTable(
        batch_rows,
        colWidths=[20 * mm, 16 * mm, 16 * mm, 122 * mm],
        repeatRows=1,
    )
    batch_table.setStyle(_table_style())
    story.extend([batch_table, PageBreak(), Paragraph("病例概览", styles["h1"])])

    case_rows = [["case_id", "series 数", "批次数", "batch_ids", "波动字段", "问题"]]
    for case in cases:
        case_rows.append(
            [
                case["case_id"],
                str(case["series_count"]),
                str(case["batch_count"]),
                ", ".join(case["batch_ids"]) or "无",
                ", ".join(case["varying_fields"]) or "无",
                format_issue_list(case["within_series_issues"]),
            ]
        )
    case_table = LongTable(
        case_rows,
        colWidths=[16 * mm, 14 * mm, 14 * mm, 22 * mm, 46 * mm, 62 * mm],
        repeatRows=1,
    )
    case_table.setStyle(_table_style())
    story.extend([case_table, PageBreak(), Paragraph("Series 详细结果", styles["h1"])])

    series_rows = [["case_id", "batch_id", "路径", "文件数", "可读数", "series 内波动字段"]]
    for item in series:
        series_rows.append(
            [
                item["case_id"],
                item["batch_id"],
                item["relative_dir"],
                str(item["file_count"]),
                str(item["readable_count"]),
                ", ".join(item["varying_parameters"]) or "无",
            ]
        )
    series_table = LongTable(
        series_rows,
        colWidths=[14 * mm, 16 * mm, 88 * mm, 14 * mm, 14 * mm, 42 * mm],
        repeatRows=1,
    )
    series_table.setStyle(_table_style())
    story.append(series_table)

    if batches:
        story.extend([PageBreak(), Paragraph("批次详细说明", styles["h1"])])
        for batch in batches:
            story.append(
                Paragraph(
                    f"<b>{batch['batch_id']}</b> / series={batch['series_count']} / case={batch['case_count']} / "
                    f"{format_mapping(batch['representative_values'])}",
                    styles["small"],
                )
            )
            story.append(Spacer(1, 4))

    doc.build(story)

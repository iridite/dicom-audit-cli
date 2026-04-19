from __future__ import annotations

import json
from pathlib import Path

from fpdf import FPDF


PAGE_W_MM = 210
PAGE_H_MM = 297
MARGIN_MM = 14
CONTENT_W_MM = PAGE_W_MM - 2 * MARGIN_MM


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
        "## 全局参数波动",
    ]

    for tag, data in summary["parameter_variation"].items():
        top_values = ", ".join(
            f"{item['value']} ({item['series_count']})"
            for item in data["top_values"][:5]
        )
        lines.append(f"- `{tag}`: 不同取值数 `{data['distinct_value_count']}`; 主要取值 {top_values or '无'}")

    lines.extend(["", "## 批次概览"])
    for batch in batches:
        lines.extend(
            [
                f"### {batch['batch_id']}",
                f"- series 数：`{batch['series_count']}`",
                f"- case 数：`{batch['case_count']}`",
                f"- 代表参数：{format_mapping(batch['representative_values'])}",
            ]
        )

    lines.extend(["", "## 病例概览"])
    for case in cases:
        lines.extend(
            [
                f"### {case['case_id']}",
                f"- series 数：`{case['series_count']}`",
                f"- 批次数：`{case['batch_count']}`",
                f"- batch_ids：{', '.join(case['batch_ids']) or '无'}",
                f"- 波动字段：{', '.join(case['varying_fields']) or '无'}",
                f"- 问题：{format_issue_list(case['within_series_issues'])}",
            ]
        )

    lines.extend(["", "## Series 详细结果"])
    for item in series:
        lines.extend(
            [
                f"### {item['case_id']} / {item['batch_id']}",
                f"- 路径：`{item['relative_dir']}`",
                f"- 文件数 / 可读数：`{item['file_count']} / {item['readable_count']}`",
                f"- series 内波动字段：{', '.join(item['varying_parameters']) or '无'}",
                f"- 分批参数：{format_mapping(item['batch_values'])}",
            ]
        )

    return "\n".join(lines) + "\n"


def write_markdown_report(path: Path, payload: dict) -> None:
    path.write_text(render_markdown_report(payload), encoding="utf-8")


def _find_windows_font() -> tuple[str, str]:
    candidates = [
        (r"C:\Windows\Fonts\SourceHanSansCN-Regular.otf", r"C:\Windows\Fonts\SourceHanSansCN-Bold.otf"),
        (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"),
        (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\simsunb.ttf"),
        (r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for regular, bold in candidates:
        if Path(regular).exists() and Path(bold).exists():
            return regular, bold
    raise FileNotFoundError("No usable Chinese font was found under C:\\Windows\\Fonts.")


class AuditPdf(FPDF):
    def __init__(self, title: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.title = title
        self.alias_nb_pages()
        self.set_auto_page_break(auto=True, margin=MARGIN_MM)
        regular_font, bold_font = _find_windows_font()
        self.add_font("AuditSans", "", regular_font)
        self.add_font("AuditSans", "B", bold_font)
        self.set_title(title)
        self.set_author("dicom-audit-cli")
        self.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)

    def header(self) -> None:
        self.set_font("AuditSans", "B", 12)
        self.set_text_color(15, 23, 42)
        self.cell(0, 8, self.title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(203, 213, 225)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.y, self.w - self.r_margin, self.y)
        self.ln(3)

    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("AuditSans", "", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, f"{self.page_no()}/{{nb}}", align="C")

    def block_title(self, text: str, level: int = 1) -> None:
        if self.y > PAGE_H_MM - 40:
            self.add_page()
        size = 14 if level == 1 else 11
        self.set_font("AuditSans", "B", size)
        self.set_text_color(15, 23, 42)
        self.ln(2)
        self.multi_cell(CONTENT_W_MM, 7 if level == 1 else 6, text)
        self.ln(1)

    def paragraph(self, text: str, size: int = 9, color: tuple[int, int, int] = (31, 41, 55)) -> None:
        self.set_font("AuditSans", "", size)
        self.set_text_color(*color)
        self.multi_cell(CONTENT_W_MM, 5.2, text)

    def bullet(self, text: str) -> None:
        self.set_font("AuditSans", "", 9)
        self.set_text_color(31, 41, 55)
        self.multi_cell(CONTENT_W_MM, 5.2, f"- {text}")

    def kv(self, label: str, value: str) -> None:
        self.set_font("AuditSans", "B", 9)
        self.set_text_color(15, 23, 42)
        self.write(5.2, f"{label}：")
        self.set_font("AuditSans", "", 9)
        self.set_text_color(31, 41, 55)
        self.write(5.2, value)
        self.ln(5.8)

    def divider(self) -> None:
        self.set_draw_color(226, 232, 240)
        self.set_line_width(0.2)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(3)


def write_pdf_report(path: Path, payload: dict) -> None:
    summary = payload["summary"]
    cases = payload["cases"]
    batches = payload["batches"]
    series = payload["series"]

    pdf = AuditPdf(payload["title"])
    pdf.add_page()

    pdf.block_title("摘要", level=1)
    pdf.kv("生成时间", summary["generated_at"])
    pdf.kv("扫描根目录", summary["root"])
    pdf.kv("候选 DICOM 文件数", str(summary["total_candidate_files"]))
    pdf.kv("series 目录数", str(summary["total_series_dirs"]))
    pdf.kv("病例数", str(summary["total_cases"]))
    pdf.kv("参数批次数", str(summary["total_batches"]))
    pdf.kv("用于分批的参数字段", ", ".join(summary["batch_fields"]))
    pdf.kv("关键检查字段", ", ".join(summary["critical_tags"]))
    pdf.kv("批次划分规则", "仅按参数签名分组，不使用病例号、目录名或期相名")

    pdf.block_title("严重度统计", level=1)
    pdf.bullet(
        f"series：正常 {summary['series_severity_counts'].get('ok', 0)}，"
        f"警告 {summary['series_severity_counts'].get('warning', 0)}，"
        f"错误 {summary['series_severity_counts'].get('error', 0)}"
    )
    pdf.bullet(
        f"case：正常 {summary['case_severity_counts'].get('ok', 0)}，"
        f"警告 {summary['case_severity_counts'].get('warning', 0)}，"
        f"错误 {summary['case_severity_counts'].get('error', 0)}"
    )

    pdf.block_title("全局参数波动", level=1)
    for tag, data in summary["parameter_variation"].items():
        top_values = "; ".join(
            f"{item['value']} ({item['series_count']})"
            for item in data["top_values"][:5]
        ) or "无"
        pdf.block_title(tag, level=2)
        pdf.bullet(f"不同取值数：{data['distinct_value_count']}")
        pdf.bullet(f"主要取值：{top_values}")

    pdf.add_page()
    pdf.block_title("批次概览", level=1)
    for batch in batches:
        pdf.block_title(batch["batch_id"], level=2)
        pdf.bullet(f"series 数：{batch['series_count']}")
        pdf.bullet(f"case 数：{batch['case_count']}")
        pdf.bullet(f"病例：{', '.join(batch['case_ids'])}")
        pdf.paragraph(format_mapping(batch["representative_values"]), size=8)
        pdf.divider()

    pdf.add_page()
    pdf.block_title("病例概览", level=1)
    for case in cases:
        pdf.block_title(case["case_id"], level=2)
        pdf.bullet(f"series 数：{case['series_count']}")
        pdf.bullet(f"批次数：{case['batch_count']}")
        pdf.bullet(f"batch_ids：{', '.join(case['batch_ids']) or '无'}")
        pdf.bullet(f"波动字段：{', '.join(case['varying_fields']) or '无'}")
        pdf.bullet(f"问题：{format_issue_list(case['within_series_issues'])}")
        pdf.divider()

    pdf.add_page()
    pdf.block_title("Series 详细结果", level=1)
    for item in series:
        pdf.block_title(f"{item['case_id']} / {item['batch_id']}", level=2)
        pdf.bullet(f"路径：{item['relative_dir']}")
        pdf.bullet(f"文件数 / 可读数：{item['file_count']} / {item['readable_count']}")
        pdf.bullet(f"series 内波动字段：{', '.join(item['varying_parameters']) or '无'}")
        pdf.paragraph(format_mapping(item["batch_values"]), size=8)
        pdf.divider()

    pdf.output(str(path))

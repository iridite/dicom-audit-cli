from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


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


def render_typst_report(json_filename: str) -> str:
    return f"""#set page(margin: 16pt)
#set text(font: ("Microsoft YaHei", "Source Han Sans CN", "SimHei", "SimSun"), size: 10pt)
#set par(justify: false, leading: 0.8em)

#let report = json("{json_filename}")

#let kv(label, value) = [
  *#label:* #value \\
]

#let section(title) = [
  #block(below: 8pt)[
    = #title
  ]
]

#let sub(title) = [
  #block(above: 6pt, below: 4pt)[
    == #title
  ]
]

#report.at("title")

#section("摘要")
#kv("生成时间", report.at("summary").at("generated_at"))
#kv("扫描根目录", report.at("summary").at("root"))
#kv("候选 DICOM 文件数", str(report.at("summary").at("total_candidate_files")))
#kv("series 目录数", str(report.at("summary").at("total_series_dirs")))
#kv("病例数", str(report.at("summary").at("total_cases")))
#kv("参数批次数", str(report.at("summary").at("total_batches")))
#kv("用于分批的参数字段", report.at("summary").at("batch_fields").join(", "))
#kv("关键检查字段", report.at("summary").at("critical_tags").join(", "))
#kv("批次划分规则", "仅按参数签名分组，不使用病例号、目录名或期相名")

#section("全局参数波动")
#for (tag, data) in report.at("summary").at("parameter_variation").pairs() [
  #sub(tag)
  #let top-values = data.at("top_values").map(item => str(item.at("value")) + " (" + str(item.at("series_count")) + ")").join("; ")
  - 不同取值数：#data.at("distinct_value_count")
  - 主要取值：#(if top-values == "" {{ "无" }} else {{ top-values }})
]

#pagebreak()
#section("批次概览")
#for batch in report.at("batches") [
  #sub(batch.at("batch_id"))
  - series 数：#batch.at("series_count")
  - case 数：#batch.at("case_count")
  - 病例：#batch.at("case_ids").join(", ")
  - 代表参数：#(batch.at("representative_values").pairs().map(pair => str(pair.first()) + "=" + str(pair.last())).join("; "))
]

#pagebreak()
#section("病例概览")
#for case in report.at("cases") [
  #sub(case.at("case_id"))
  - series 数：#case.at("series_count")
  - 批次数：#case.at("batch_count")
  - batch_ids：#(if case.at("batch_ids").len() == 0 {{ "无" }} else {{ case.at("batch_ids").join(", ") }})
  - 波动字段：#(if case.at("varying_fields").len() == 0 {{ "无" }} else {{ case.at("varying_fields").join(", ") }})
  - 问题：#(if case.at("within_series_issues").len() == 0 {{ "无" }} else {{ case.at("within_series_issues").join(", ") }})
]

#pagebreak()
#section("Series 详细结果")
#for item in report.at("series") [
  #sub(item.at("case_id") + " / " + item.at("batch_id"))
  - 路径：#item.at("relative_dir")
  - 文件数 / 可读数：#str(item.at("file_count")) + " / " + str(item.at("readable_count"))
  - series 内波动字段：#(if item.at("varying_parameters").len() == 0 {{ "无" }} else {{ item.at("varying_parameters").join(", ") }})
  - 分批参数：#(item.at("batch_values").pairs().map(pair => str(pair.first()) + "=" + str(pair.last())).join("; "))
]
"""


def write_typst_report(path: Path, json_report_path: Path) -> None:
    path.write_text(render_typst_report(json_report_path.name), encoding="utf-8")


def find_typst_binary(explicit_path: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if path.exists():
            return path

    from_path = shutil.which("typst")
    if from_path:
        return Path(from_path).resolve()

    argv_parent = Path(sys.argv[0]).resolve().parent
    cwd = Path.cwd().resolve()
    candidates.extend(
        [
            argv_parent / "typst.exe",
            argv_parent / "typst",
            cwd / "typst.exe",
            cwd / "typst",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def compile_typst_pdf(typst_binary: Path, typ_path: Path, pdf_path: Path) -> None:
    subprocess.run(
        [str(typst_binary), "compile", str(typ_path), str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

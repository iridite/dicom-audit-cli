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


def _typst_string(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def _batch_device_line(batch: dict) -> str:
    values = batch["representative_values"]
    return f"{values.get('Modality', '无')} · {values.get('Manufacturer', '无')} / {values.get('ManufacturerModelName', '无')}"


def _batch_geometry_line(batch: dict) -> str:
    values = batch["representative_values"]
    return (
        f"{values.get('Rows', '无')}×{values.get('Columns', '无')} · "
        f"spacing {values.get('PixelSpacing', '无')} · "
        f"thickness {values.get('SliceThickness', '无')}"
    )


def _batch_recon_line(batch: dict) -> str:
    values = batch["representative_values"]
    return f"kernel {values.get('ConvolutionKernel', '无')} · KVP {values.get('KVP', '无')}"


def _spotlight_params(summary: dict, limit: int = 6) -> list[tuple[str, dict]]:
    items = list(summary["parameter_variation"].items())
    items.sort(key=lambda item: (-item[1]["distinct_value_count"], item[0]))
    return items[:limit]


FIELD_LABELS = {
    "Modality": "Modality",
    "Manufacturer": "厂商",
    "ManufacturerModelName": "机型",
    "Rows": "Rows",
    "Columns": "Columns",
    "PixelSpacing": "PixelSpacing",
    "SliceThickness": "SliceThickness",
    "ImageOrientationPatient": "Orientation",
    "ConvolutionKernel": "Kernel",
    "KVP": "KVP",
}


def _case_comparison_lines(case: dict, batch_map: dict[str, dict]) -> list[str]:
    fields = case["varying_fields"]
    if not fields:
        return []
    lines: list[str] = []
    for batch_id in case["batch_ids"]:
        batch = batch_map[batch_id]
        values = batch["representative_values"]
        pieces = [f"{FIELD_LABELS.get(field, field)}={values.get(field, '无')}" for field in fields]
        lines.append(f"{batch_id}: " + " / ".join(pieces))
    return lines


def render_typst_report(payload: dict) -> str:
    summary = payload["summary"]
    batches = payload["batches"]
    cases = payload["cases"]
    series = payload["series"]
    batch_map = {batch["batch_id"]: batch for batch in batches}

    metric_cards = [
        ("病例数", summary["total_cases"], "扫描根目录下识别到的病例目录"),
        ("series 目录数", summary["total_series_dirs"], "实际纳入参数审计的目录"),
        ("参数批次数", summary["total_batches"], "仅按参数签名分组"),
        ("候选 DICOM 文件数", summary["total_candidate_files"], "递归扫描到的候选文件"),
    ]

    cover_metrics = ",\n  ".join(
        f"metric-card({_typst_string(label)}, {_typst_string(value)}, {_typst_string(note)})"
        for label, value, note in metric_cards
    )

    spotlight_blocks = []
    for tag, data in _spotlight_params(summary, limit=4):
        top_values = "; ".join(
            f"{item['value']} ({item['series_count']})"
            for item in data["top_values"][:4]
        ) or "无"
        spotlight_blocks.append(
            f"spot-card({_typst_string(tag)}, {_typst_string(str(data['distinct_value_count']) + ' 个不同取值')}, {_typst_string(top_values)})"
        )
    spotlight_cards = ",\n  ".join(spotlight_blocks)

    batch_blocks = []
    for batch in batches:
        batch_blocks.append(
            f"""#batch-card(
  {_typst_string(batch["batch_id"])},
  {_typst_string(f"series {batch['series_count']} · case {batch['case_count']}")},
  {_typst_string(_batch_device_line(batch))},
  {_typst_string(_batch_geometry_line(batch))},
  {_typst_string(_batch_recon_line(batch))},
  {_typst_string(", ".join(batch["case_ids"]))},
)"""
        )
    batch_cards = "\n  ".join(batch_blocks)

    case_blocks = []
    for case in cases:
        status_text = "单一参数批次" if case["batch_count"] <= 1 else "存在参数变档"
        status_kind = "stable" if case["batch_count"] <= 1 else "changed"
        issue_text = format_issue_list(case["within_series_issues"])
        comparison_lines = _case_comparison_lines(case, batch_map)
        comparison_block = "[]"
        if comparison_lines:
            comparison_items = "\n    ".join(
                f"#bullet-line({_typst_string(line)})" for line in comparison_lines
            )
            comparison_block = f"""[
    #section-mini({_typst_string("批次间参数对比")})
    {comparison_items}
  ]"""
        highlight_block = (
            f"highlight-card({_typst_string('参数变档字段')}, {_typst_string(' · '.join(FIELD_LABELS.get(field, field) for field in case['varying_fields']))})"
            if case["varying_fields"]
            else f"highlight-card({_typst_string('参数状态')}, {_typst_string('该病例下各 series 落在同一参数批次内')}, kind: \"stable\")"
        )
        case_blocks.append(
            f"""#case-card(
  {_typst_string(case["case_id"])},
  {_typst_string(status_text)},
  kind: {_typst_string(status_kind)},
  summary: {_typst_string(f"{case['series_count']} 个 series，涉及 {case['batch_count']} 个批次：" + (', '.join(case['batch_ids']) if case['batch_ids'] else '无'))},
  issues: {_typst_string(issue_text)},
  highlight: {highlight_block},
  compare: {comparison_block},
)"""
        )
    case_cards = "\n".join(case_blocks)

    appendix_blocks = []
    for item in series:
        appendix_blocks.append(
            f"""#appendix-card(
  {_typst_string(item["case_id"] + " / " + item["batch_id"])},
  {_typst_string(item["relative_dir"])},
  {_typst_string(f"{item['file_count']} / {item['readable_count']}")},
  {_typst_string(", ".join(item["varying_parameters"]) if item["varying_parameters"] else "无")},
  {_typst_string(format_mapping(item["batch_values"]))},
)"""
        )
    appendix_cards = "\n".join(appendix_blocks)

    return f"""#set page(margin: (x: 18pt, y: 20pt))
#set text(font: ("Microsoft YaHei", "SimHei", "SimSun"), size: 10pt)
#set par(justify: false, leading: 0.9em)
#set heading(numbering: none, outlined: false)

#let ink = rgb("#0f172a")
#let muted = rgb("#64748b")
#let line = rgb("#dbe3ec")
#let soft = rgb("#f8fafc")
#let brand = rgb("#0f766e")
#let warn-fill = rgb("#fff7ed")
#let warn-ink = rgb("#c2410c")
#let alert-fill = rgb("#fff1f2")
#let alert-ink = rgb("#be123c")
#let stable-fill = rgb("#ecfeff")
#let stable-ink = rgb("#0f766e")

#let soft-card(body, fill: soft, stroke: line) = block(
  fill: fill,
  stroke: stroke,
  radius: 9pt,
  inset: 10pt,
  width: 100%,
)[#body]

#let metric-card(label, value, note) = soft-card[
  #text(size: 8pt, fill: muted)[#label]
  #v(4pt)
  #text(size: 22pt, weight: "bold", fill: ink)[#value]
  #v(4pt)
  #text(size: 8pt, fill: muted)[#note]
]

#let spot-card(title, stat, detail) = soft-card[
  #text(size: 9pt, weight: "bold", fill: ink)[#title]
  #v(2pt)
  #text(size: 14pt, weight: "bold", fill: brand)[#stat]
  #v(4pt)
  #text(size: 8pt, fill: muted)[#detail]
]

#let badge(label, fill: warn-fill, ink-color: warn-ink) = box(
  fill: fill,
  inset: (x: 8pt, y: 4pt),
  radius: 999pt,
)[#text(size: 8pt, weight: "bold", fill: ink-color)[#label]]

#let section-mini(label) = [
  #text(size: 9pt, weight: "bold", fill: ink)[#label]
  #v(3pt)
]

#let bullet-line(label) = [
  #text(size: 8.5pt, fill: ink)[• #label]
  #v(2pt)
]

#let batch-card(id, counts, device, geometry, recon, cases) = soft-card[
  #text(size: 12pt, weight: "bold", fill: ink)[#id]
  #v(2pt)
  #text(size: 8pt, fill: muted)[#counts]
  #v(6pt)
  #text(size: 8.5pt, weight: "bold", fill: ink)[设备]
  #linebreak()
  #text(size: 8.5pt)[#device]
  #v(4pt)
  #text(size: 8.5pt, weight: "bold", fill: ink)[几何]
  #linebreak()
  #text(size: 8.5pt)[#geometry]
  #v(4pt)
  #text(size: 8.5pt, weight: "bold", fill: ink)[重建]
  #linebreak()
  #text(size: 8.5pt)[#recon]
  #v(4pt)
  #text(size: 8.5pt, weight: "bold", fill: ink)[病例]
  #linebreak()
  #text(size: 8.5pt)[#cases]
]

#let highlight-card(title, value, kind: "changed") = {{
  let fill = if kind == "stable" {{ stable-fill }} else {{ alert-fill }}
  let fg = if kind == "stable" {{ stable-ink }} else {{ alert-ink }}
  soft-card(fill: fill, stroke: fill)[
    #text(size: 8pt, weight: "bold", fill: fg)[#title]
    #v(3pt)
    #text(size: 10pt, weight: "bold", fill: fg)[#value]
  ]
}}

#let case-card(id, status, kind: "changed", summary: "", issues: "", highlight: [], compare: []) = soft-card[
  #text(size: 12pt, weight: "bold", fill: ink)[病例 #id]
  #h(8pt)
  #badge(status, fill: if kind == "stable" {{ stable-fill }} else {{ warn-fill }}, ink-color: if kind == "stable" {{ stable-ink }} else {{ warn-ink }})
  #v(8pt)
  #text(size: 8.5pt, fill: muted)[#summary]
  #v(8pt)
  #highlight
  #if compare != [] [
    #v(8pt)
    #compare
  ]
  #if issues != "无" [
    #v(8pt)
    #section-mini("附加问题")
    #text(size: 8.5pt, fill: muted)[#issues]
  ]
]

#let appendix-card(title, path, counts, varies, batch-values) = soft-card[
  #text(size: 10pt, weight: "bold", fill: ink)[#title]
  #v(4pt)
  #text(size: 8pt, fill: muted)[路径：#path]
  #v(2pt)
  #text(size: 8pt)[文件数 / 可读数：#counts]
  #linebreak()
  #text(size: 8pt)[series 内波动字段：#varies]
  #v(4pt)
  #text(size: 8pt, fill: muted)[#batch-values]
]

#align(center)[
  #v(16pt)
  #text(size: 28pt, weight: "bold", fill: ink)[{payload["title"]}]
  #v(6pt)
  #text(size: 11pt, fill: muted)[DICOM 参数批次与整体波动审计]
  #v(10pt)
]

#soft-card(fill: rgb("#eff6ff"), stroke: rgb("#bfdbfe"))[
  #text(size: 9pt, weight: "bold", fill: rgb("#1d4ed8"))[批次划分规则]
  #v(4pt)
  #text(size: 9pt, fill: rgb("#1e3a8a"))[
    仅按参数签名分组，不使用病例号、目录名或期相名。
    重点回答：有多少个参数批次、哪些参数存在波动、哪些病例发生了明显参数变档。
  ]
]

#v(10pt)
#grid(columns: (1fr, 1fr), gutter: 10pt,
  {cover_metrics}
)

#v(12pt)
= 参数波动聚焦
#grid(columns: (1fr, 1fr), gutter: 10pt,
  {spotlight_cards}
)

#pagebreak()
= 批次概览
#columns(2, gutter: 12pt)[
  {batch_cards}
]

#pagebreak()
= 病例波动摘要
{case_cards}

#pagebreak()
= Series 附录
{appendix_cards}
"""


def write_typst_report(path: Path, payload: dict) -> None:
    path.write_text(render_typst_report(payload), encoding="utf-8")


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

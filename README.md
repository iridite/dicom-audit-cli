# DICOM Audit CLI

一个独立的 DICOM 审计工具，支持：

- Python CLI
- Windows 单文件 `exe`
- JSON / Markdown / PDF 报告输出

主输入是一个根目录。工具会递归扫描下面的 DICOM 文件，自动完成：

- 目录与文件发现
- series 级技术完整性检查
- case 级三期完整性归并
- JSON 报告输出
- Markdown 报告输出
- PDF 报告输出

## 适用场景

- CT / MR / 通用 DICOM 数据完整性审计
- 递归扫描医生或项目方给到的原始 DICOM 文件夹
- 快速生成可发给他人的 PDF 审计报告

## 运行方式

### 1. Windows 直接运行 EXE

发布版会提供 `dicom-audit.exe`，医生电脑上不需要安装 Python。

```powershell
.\dicom-audit.exe --root "D:\CT_Study_Export"
```

### 2. Windows / PowerShell 启动器

仓库里自带 `run_dicom_audit.cmd`，依赖 `uv`。

```powershell
.\run_dicom_audit.cmd --root "D:\CT_Study_Export"
```

### 3. 直接用 uv

```powershell
uv run --project . dicom-audit --root "D:\CT_Study_Export"
```

### 4. 如果本机已有 Python

```powershell
python -m dicom_audit_cli --root "D:\CT_Study_Export"
```

## 常用参数

```powershell
.\dicom-audit.exe `
  --root "D:\CT_Study_Export" `
  --output-dir ".\output\audit_001" `
  --title "DICOM 技术完整性审计报告" `
  --modality CT `
  --phase-alias AP=arterial `
  --phase-alias PVP=portal `
  --phase-alias NC=noncontrast
```

## 参数说明

- `--root`：必填，递归扫描的根目录
- `--output-dir`：输出目录，默认当前工作目录下生成时间戳目录
- `--title`：报告标题
- `--modality`：期望模态，默认 `CT`
- `--expected-phases`：期望期相，默认 `arterial,portal,noncontrast`
- `--phase-alias`：自定义期相别名，例如 `AP=arterial`
- `--exclude-dir`：递归扫描时跳过的目录名，可重复传入
- `--suffix`：候选文件后缀，默认 `.dcm`
- `--all-files`：不按后缀过滤，尝试读取全部文件
- `--case-regex`：从路径推断病例号时使用的目录名正则，默认 `^\d+$`

## 默认输出

工具会在输出目录里生成：

- `dicom_audit_report.json`
- `dicom_audit_report.md`
- `dicom_audit_report.pdf`

## 当前默认期相映射

- `AP -> arterial`
- `PVP -> portal`
- `NC -> noncontrast`

如果目录命名不同，可通过 `--phase-alias` 补充。

## Windows EXE 打包

仓库内置打包脚本：

```powershell
.\build_windows_exe.cmd
```

默认输出：

- `dist\dicom-audit.exe`

## 当前验证

该版本已经在 Windows 上做过真实目录扫描验证，并成功生成：

- JSON 报告
- Markdown 报告
- PDF 报告
- 单文件 `exe`

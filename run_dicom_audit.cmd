@echo off
setlocal
set SCRIPT_DIR=%~dp0.
uv run --project "%SCRIPT_DIR%" dicom-audit %*
endlocal

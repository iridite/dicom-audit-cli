@echo off
setlocal
set REPO_DIR=%~dp0.
if exist "%REPO_DIR%\dist\dicom-audit.exe" del /f /q "%REPO_DIR%\dist\dicom-audit.exe"
uv run --project "%REPO_DIR%" --group dev pyinstaller ^
  --clean ^
  --noconfirm ^
  --onefile ^
  --name dicom-audit ^
  --paths "%REPO_DIR%\\src" ^
  "%REPO_DIR%\\src\\dicom_audit_cli\\__main__.py"
endlocal

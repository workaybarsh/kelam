# Kelam exe build script
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
#
# Single file (onefile): dist\Kelam.exe
# The bridge is started with a clean environment, so the temp-folder warning
# does not appear.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

python -m pip install --quiet --upgrade pyinstaller

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name Kelam `
    --icon "assets\kelam.ico" `
    --add-data "assets;assets" `
    --add-data "LICENSE;." `
    --add-data "README.md;." `
    main.py

Write-Host ""
Write-Host "Ready: dist\Kelam.exe" -ForegroundColor Green

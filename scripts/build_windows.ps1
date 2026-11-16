<#
.SYNOPSIS
    Build the installable Windows package of WhatsApp Forensic Studio AI.

.DESCRIPTION
    Runs the full release pipeline on a Windows 10/11 x64 machine:

      1. verify toolchain (Rust stable MSVC, Node 20+, Python 3.12)
      2. install frontend + engine dependencies
      3. freeze the Python engine into a sidecar binary
      4. run the engine test suite
      5. typecheck and build the frontend
      6. `tauri build`, producing the NSIS installer, MSI and portable exe

    Output:
      src-tauri/target/release/bundle/nsis/*.exe
      src-tauri/target/release/bundle/msi/*.msi
      src-tauri/target/release/whatsapp-forensic-studio.exe

.EXAMPLE
    pwsh -File scripts/build_windows.ps1
    pwsh -File scripts/build_windows.ps1 -SkipTests
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipSidecar
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Assert-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Missing '$name'. $hint"
    }
}

Write-Host "== Toolchain ==" -ForegroundColor Cyan
Assert-Command cargo "Install Rust from https://rustup.rs (MSVC toolchain) and Visual Studio Build Tools."
Assert-Command node "Install Node.js 20 or newer."
Assert-Command python "Install Python 3.12 (64-bit)."
$rustTargets = cargo target list --installed
if ($rustTargets -notcontains "x86_64-pc-windows-msvc") {
    throw "Add the MSVC target: rustup target add x86_64-pc-windows-msvc"
}
node --version
cargo --version
python --version

Write-Host "== Dependencies ==" -ForegroundColor Cyan
npm ci
python -m venv .venv
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r forensic-engine\requirements.txt

if (-not $SkipTests) {
    Write-Host "== Engine tests ==" -ForegroundColor Cyan
    Push-Location forensic-engine
    $env:PYTHONPATH = (Get-Location).Path
    & $venvPython -m pytest -q
    Pop-Location
}

if (-not $SkipSidecar) {
    Write-Host "== Freeze engine sidecar ==" -ForegroundColor Cyan
    $env:PYTHON = $venvPython
    bash scripts/build_sidecar.sh x86_64-pc-windows-msvc
}

Write-Host "== Frontend ==" -ForegroundColor Cyan
npm run build

Write-Host "== Installer ==" -ForegroundColor Cyan
npm run tauri:build

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Get-ChildItem -Path "src-tauri\target\release\bundle" -Recurse -Include *.exe, *.msi |
    ForEach-Object { Write-Host ("  " + $_.FullName) }
Write-Host ""
Write-Host "Smoke test on a clean machine:"
Write-Host "  1. install the NSIS package as a standard user"
Write-Host "  2. launch from the Start menu, create a case, import forensic-engine\tests\fixtures\android_24h.txt"
Write-Host "  3. confirm the dashboard populates and Search returns rows"
Write-Host "  4. uninstall and confirm the case directory under %APPDATA% is preserved"

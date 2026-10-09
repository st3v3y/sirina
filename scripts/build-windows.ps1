# Build the Sirina Windows installer (NSIS): freeze the Python backend, build the Rust
# system-audio helper, and bundle both into the Tauri app. No signing.
#
# Prereqs: Rust (MSVC toolchain), uv, Node >= 18, and the WebView2 runtime (preinstalled
# on Windows 10/11). The Tauri CLI is `cargo tauri` if installed, else the frontend's
# pinned @tauri-apps/cli.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "  x $cmd not found - $hint"
    $script:missing = $true
  }
}
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" } }

Write-Host "==> Checking prerequisites"
$missing = $false
Need cargo "install Rust: https://rustup.rs"
Need uv "install uv: https://docs.astral.sh/uv/getting-started/installation/"
Need npm "install Node >= 18"
if ($missing) { throw "Install the items above and re-run." }

function Invoke-Tauri {
  # `cargo tauri` if installed, else the frontend's pinned @tauri-apps/cli. Check for the
  # binary instead of running it: a failing native command with redirected stderr aborts
  # the script under Windows PowerShell 5.1.
  if (Get-Command cargo-tauri -ErrorAction SilentlyContinue) { cargo tauri @args }
  else { npm run --prefix (Join-Path $Root "frontend") tauri @args }
}

Write-Host "==> Building frontend"
Set-Location (Join-Path $Root "frontend")
npm run build; Check "frontend build"

Write-Host "==> Freezing backend with PyInstaller"
Set-Location (Join-Path $Root "backend")
uv run python -m PyInstaller packaging/backend.spec --noconfirm --distpath dist --workpath build
Check "PyInstaller"

$Res = Join-Path $Root "frontend\src-tauri\resources"
Write-Host "==> Placing backend and helper into Tauri resources"
if (Test-Path $Res) { Remove-Item -Recurse -Force $Res }
New-Item -ItemType Directory -Force $Res | Out-Null
Copy-Item -Recurse (Join-Path $Root "backend\dist\backend") (Join-Path $Res "backend")

& (Join-Path $Root "native\system-audio-capture-rs\build.ps1"); Check "helper build"
Copy-Item (Join-Path $Root "native\system-audio-capture-rs\target\release\system-audio-capture.exe") $Res

Write-Host "==> Building the Tauri installer"
Set-Location (Join-Path $Root "frontend\src-tauri")
Invoke-Tauri build; Check "tauri build"

$Bundle = Join-Path $Root "frontend\src-tauri\target\release\bundle\nsis"
Write-Host ""
Write-Host "Done. Installer: $(Get-ChildItem $Bundle -Filter *.exe | Select-Object -ExpandProperty FullName)"
Write-Host "Unsigned: on first run choose 'More info' -> 'Run anyway' in the SmartScreen prompt."
Write-Host "The app needs a local Ollama (http://localhost:11434) or another AI provider set in Settings."

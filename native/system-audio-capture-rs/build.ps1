# Build the system-audio-capture helper for Windows (and run its unit tests). Needs Rust
# (MSVC toolchain).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
cargo test --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cargo build --release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Built $PSScriptRoot\target\release\system-audio-capture.exe"
Write-Host "Probe:   target\release\system-audio-capture.exe --probe   (exit 0 = available)"

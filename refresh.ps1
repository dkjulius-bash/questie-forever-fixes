# Wrapper for refresh.py: creates the venv on first run, then runs the pipeline.
$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating .venv and installing lupa..."
    python -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $py -m pip install lupa
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $py -I (Join-Path $PSScriptRoot "refresh.py") @args
exit $LASTEXITCODE

# Wrapper for refresh.py: sets up .venv and the QuestieTrace extractor on first run, then runs the pipeline.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    # Find a Python 3.12+; a missing launcher or the Microsoft Store "python" stub must not abort the script.
    $base = $null
    foreach ($cand in @(@("py", "-3"), @("python"))) {
        if (-not (Get-Command $cand[0] -ErrorAction SilentlyContinue)) { continue }
        $rest = @($cand | Select-Object -Skip 1)
        try {
            & $cand[0] @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { $base = $cand; break }
        } catch { }
    }
    if (-not $base) {
        Write-Host 'Python 3.12 or newer not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), open a new terminal and rerun .\refresh.ps1.'
        exit 1
    }
    Write-Host "Creating .venv and installing lupa..."
    $rest = @($base | Select-Object -Skip 1)
    & $base[0] @rest -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $py -m pip install lupa
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($args -notcontains "--archive-only") {
    $qt = Join-Path $root "vendor\QuestieTrace"
    if (-not (Test-Path (Join-Path $qt "tools\corrections-extractor\src"))) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Host "Git not found. Install Git from https://git-scm.com, or download the QuestieTrace zip from https://github.com/Questie/QuestieTrace and extract it to vendor\QuestieTrace, then rerun .\refresh.ps1."
            exit 1
        }
        Write-Host "Cloning QuestieTrace into vendor\QuestieTrace..."
        & git clone https://github.com/Questie/QuestieTrace $qt
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Host "Node.js 24 not found. Install the LTS from https://nodejs.org, open a new terminal and rerun."
        exit 1
    }
}
& $py -I (Join-Path $root "refresh.py") @args
exit $LASTEXITCODE

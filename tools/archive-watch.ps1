# Keeps every QuestieTrace session, even after QuestieTrace prunes it (it keeps only 10 per character).
# WoW rewrites QuestieTrace.lua on every /reload, logout and exit. This watcher copies any new sessions into
# archive/sessions/ each time that happens, via `refresh.py --archive-only` (idempotent, deduplicated).
# Run it in the background: tools\install-archive-watch.ps1 registers it as a hidden scheduled task at logon.
param([string]$Wow = "C:\Program Files (x86)\World of Warcraft\_forever_")

$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\python.exe"
$log  = Join-Path $root "work\archive-watch.log"
New-Item -ItemType Directory -Force (Join-Path $root "work") | Out-Null

function Invoke-Archive {
    "[$(Get-Date -Format s)] archiving" | Add-Content $log
    & $py -I (Join-Path $root "refresh.py") --wow $Wow --archive-only *>> $log
}

Invoke-Archive   # catch anything written while the watcher wasn't running

$fsw = New-Object IO.FileSystemWatcher (Join-Path $Wow "WTF\Account"), "QuestieTrace.lua"
$fsw.IncludeSubdirectories = $true
$fsw.NotifyFilter = [IO.NotifyFilters]'LastWrite, FileName'
while ($true) {
    $r = $fsw.WaitForChanged([IO.WatcherChangeTypes]'Changed, Created, Renamed', 60000)
    if ($r.TimedOut) { continue }
    Start-Sleep -Seconds 10   # let WoW finish writing all characters' files
    Invoke-Archive
}

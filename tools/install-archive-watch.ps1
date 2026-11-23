# Registers tools\archive-watch.ps1 as a scheduled task that starts hidden at every logon of the current user,
# and starts it now. Re-running it replaces the existing task.
#   .\tools\install-archive-watch.ps1              # install / update
#   .\tools\install-archive-watch.ps1 -Uninstall   # remove
# The watcher is launched through `conhost.exe --headless`: on Windows 11 the default terminal (Windows Terminal)
# ignores `pwsh -WindowStyle Hidden`, which would leave a console window open.
param(
    [string]$Wow = "C:\Program Files (x86)\World of Warcraft\_forever_",
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$name = "QuestieTrace archive watcher"

if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $name
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
}
# Stopping the task does not always end a watcher launched through conhost --headless; end any leftovers.
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*archive-watch.ps1*' -and $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if ($Uninstall) { Write-Host "Removed '$name'."; return }

$script = Join-Path $PSScriptRoot "archive-watch.ps1"
$shell  = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $shell) { $shell = (Get-Command powershell).Source }
$arg = "--headless `"$shell`" -NoProfile -ExecutionPolicy Bypass -File `"$script`" -Wow `"$Wow`""

Register-ScheduledTask -TaskName $name `
    -Description "Copies new QuestieTrace sessions into questie-forever-fixes\archive whenever WoW saves them." `
    -Trigger  (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) `
    -Action   (New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR "System32\conhost.exe") -Argument $arg) `
    -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) | Out-Null
Start-ScheduledTask -TaskName $name
Write-Host "Installed and started '$name'. Log: $(Join-Path (Split-Path -Parent $PSScriptRoot) 'work\archive-watch.log')"

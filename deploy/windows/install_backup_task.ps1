param(
    [Parameter(Mandatory = $true)] [string] $ApplicationRoot,
    [Parameter(Mandatory = $true)] [string] $ServiceUser,
    [string] $DailyAt = '01:30'
)

$resolvedRoot = (Resolve-Path -LiteralPath $ApplicationRoot).Path
$pythonPath = Join-Path $resolvedRoot '.venv\Scripts\python.exe'
$managePath = Join-Path $resolvedRoot 'manage.py'
if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $managePath)) {
    throw 'ApplicationRoot must contain manage.py and the WMS .venv.'
}

$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$managePath`" backup_wms" -WorkingDirectory $resolvedRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName 'WMS Daily Backup' -Action $action -Trigger $trigger -Settings $settings -User $ServiceUser -RunLevel Highest

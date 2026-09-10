# Tear down a source install so it can be set up again cleanly.
#
#   .\tools\uninstall.ps1 -DryRun     # show what would happen, change nothing
#   .\tools\uninstall.ps1             # stop + unregister, keep your data
#   .\tools\uninstall.ps1 -PurgeData  # also delete enrollment + stored password
#   .\tools\uninstall.ps1 -RemoveVenv # also delete .venv
#
# Reinstall afterwards with .\install.cmd (or bootstrap.ps1).
#
# Unregistering the Credential Provider needs administrator rights; this
# script elevates that one step for you.
param(
    [switch]$PurgeData,
    [switch]$RemoveVenv,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$home_dir = Join-Path $env:USERPROFILE '.face-unlock'

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Would($msg) { if ($DryRun) { Write-Host "    [dry-run] $msg" -ForegroundColor Yellow; return $true } return $false }

# 1. Scheduled tasks -------------------------------------------------------
Step 'Scheduled tasks'
foreach ($name in 'FaceUnlock-Service', 'FaceUnlock-Presence') {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { Write-Host "    $name : absent"; continue }
    if (Would "unregister $name (state $($task.State))") { continue }
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host "    $name : unregistered"
}

# 2. Running processes -----------------------------------------------------
Step 'Processes'
$procs = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*face_service*' -or $_.CommandLine -like '*presence_monitor*' }
if (-not $procs) { Write-Host '    none running' }
foreach ($p in $procs) {
    if (Would "kill PID $($p.ProcessId)") { continue }
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "    killed PID $($p.ProcessId)"
}

# 3. Credential Provider ---------------------------------------------------
Step 'Credential Provider registration'
$clsid = '{F50C7625-CF2E-4572-A0CB-BCF578F9BECA}'
$cpKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
if (-not (Test-Path $cpKey)) {
    Write-Host '    not registered'
} elseif (-not (Would 'unregister the Credential Provider DLL (elevates)')) {
    $reg = Join-Path $root 'credential_provider\register.ps1'
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $reg, '-Action', 'unregister'
    )
    Write-Host "    still registered: $(Test-Path $cpKey)"
}

# 4. Your data -------------------------------------------------------------
Step 'User data'
# signing\ is deliberately never touched: it holds the code-signing key,
# which has nothing to do with an install.
$dataItems = @('config.toml', 'embeddings.npz', 'credentials.bin', 'service.log', 'presence.log', 'enroll')
if (-not $PurgeData) {
    Write-Host "    kept $home_dir (pass -PurgeData to delete enrollment + password)"
} else {
    foreach ($item in $dataItems) {
        $path = Join-Path $home_dir $item
        if (-not (Test-Path $path)) { continue }
        if (Would "delete $path") { continue }
        Remove-Item $path -Recurse -Force
        Write-Host "    deleted $item"
    }
}

# 5. Virtual environment ---------------------------------------------------
Step 'Virtual environment'
$venv = Join-Path $root '.venv'
if (-not $RemoveVenv) {
    Write-Host "    kept $venv (pass -RemoveVenv to delete)"
} elseif (Test-Path $venv) {
    if (-not (Would "delete $venv")) {
        Remove-Item $venv -Recurse -Force
        Write-Host '    deleted .venv'
    }
} else {
    Write-Host '    absent'
}

Write-Host ''
Write-Host 'Done. Reinstall with:  .\install.cmd' -ForegroundColor Green
if (-not $PurgeData) {
    Write-Host 'Your enrollment and stored password are still in place, so the wizard' -ForegroundColor Green
    Write-Host 'will show steps 2 and 3 as already satisfied.' -ForegroundColor Green
}

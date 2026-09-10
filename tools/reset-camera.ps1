# Recover a webcam that refuses to stream. Run as Administrator.
#
#   .\tools\reset-camera.ps1
#
# Two failure modes this fixes:
#   * a process died holding the camera open, so DirectShow hands out black
#     frames or refuses to open the device;
#   * the Windows Camera Frame Server keeps the pipeline half-allocated, and
#     the Camera app reports 0xA00F429F / 0xC00D7167
#     (MF_E_HW_MFT_FAILED_START_STREAMING).
#
# It restarts the frame server, then disables and re-enables the device -
# the software equivalent of unplugging it.
param([string]$InstanceId, [switch]$SkipFrameServer)

$ErrorActionPreference = 'Stop'

$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Error "Run this from an Administrator PowerShell." }

if (-not $SkipFrameServer) {
    Write-Host "Restarting the camera frame server"
    foreach ($svc in 'FrameServerMonitor', 'FrameServer') {
        $s = Get-Service $svc -ErrorAction SilentlyContinue
        if (-not $s) { continue }
        if ($s.Status -eq 'Running') {
            Stop-Service $svc -Force -ErrorAction SilentlyContinue
            Write-Host "  stopped $svc"
        }
    }
    Start-Sleep -Seconds 2
    # Both are Manual/Trigger-start: Windows brings them back when an app
    # next asks for a camera, so do not force them running here.
}

if (-not $InstanceId) {
    $dev = Get-PnpDevice -Class Camera -PresentOnly | Select-Object -First 1
    if (-not $dev) { Write-Error "No camera device found." }
    $InstanceId = $dev.InstanceId
}

Write-Host "Resetting $InstanceId"
Disable-PnpDevice -InstanceId $InstanceId -Confirm:$false
Start-Sleep -Seconds 3
Enable-PnpDevice -InstanceId $InstanceId -Confirm:$false
Start-Sleep -Seconds 5

$dev = Get-PnpDevice -InstanceId $InstanceId
Write-Host "Status: $($dev.Status)  Problem: $($dev.Problem)"
Write-Host ""
Write-Host "Now test with:" -ForegroundColor Yellow
Write-Host '  .\.venv\Scripts\python -m tools.camera_check'

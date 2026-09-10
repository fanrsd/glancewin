# Power-cycle the webcam driver. Run as Administrator.
#
#   .\tools\reset-camera.ps1
#
# A UVC webcam can end up streaming all-black frames after a process dies
# holding it open (DirectShow keeps the pin allocated). Disable + enable the
# device is the software equivalent of unplugging it.
param([string]$InstanceId)

$ErrorActionPreference = 'Stop'

$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Error "Run this from an Administrator PowerShell." }

if (-not $InstanceId) {
    $dev = Get-PnpDevice -Class Camera -PresentOnly | Select-Object -First 1
    if (-not $dev) { Write-Error "No camera device found." }
    $InstanceId = $dev.InstanceId
}

Write-Host "Resetting $InstanceId"
Disable-PnpDevice -InstanceId $InstanceId -Confirm:$false
Start-Sleep -Seconds 3
Enable-PnpDevice -InstanceId $InstanceId -Confirm:$false
Start-Sleep -Seconds 4
Write-Host "Status: $((Get-PnpDevice -InstanceId $InstanceId).Status)"

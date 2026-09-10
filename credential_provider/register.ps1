# Register or unregister the Face Unlock Credential Provider.
# Must be run as Administrator.
param(
    [ValidateSet('register','unregister')]
    [string]$Action = 'register',
    [string]$DllPath = "$PSScriptRoot\build\Release\FaceCredentialProvider.dll"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $DllPath)) {
    Write-Error "DLL not found at $DllPath. Build the project first (see README)."
    exit 1
}
$DllPath = (Resolve-Path $DllPath).Path

# regsvr32 /s writes nothing on failure, so an unelevated run used to print
# "Registered" while touching nothing. Refuse instead.
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Error "Run this from an elevated PowerShell (Run as Administrator)."
    exit 1
}

$clsid = '{F50C7625-CF2E-4572-A0CB-BCF578F9BECA}'
$cpKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"

# regsvr32 is a GUI-subsystem binary: PowerShell does not wait for it, so a
# bare call followed by Test-Path checks the registry before the write lands.
function Invoke-RegSvr {
    param([string[]]$Arguments)
    $p = Start-Process regsvr32 -ArgumentList $Arguments -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Write-Error "regsvr32 exited $($p.ExitCode)"
        exit 1
    }
}

if ($Action -eq 'register') {
    Invoke-RegSvr @('/s', $DllPath)
    if (-not (Test-Path $cpKey)) {
        Write-Error "regsvr32 succeeded but $cpKey was not created."
        exit 1
    }
    Write-Host "Registered $DllPath"
    Write-Host "Lock with Win+L and pick the Face Unlock tile."
} else {
    Invoke-RegSvr @('/u', '/s', $DllPath)
    if (Test-Path $cpKey) {
        Write-Error "Unregister failed: $cpKey still present."
        exit 1
    }
    Write-Host "Unregistered $DllPath"
}

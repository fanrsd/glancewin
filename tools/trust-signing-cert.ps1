# Trust this project's code-signing certificate on THIS machine.
# Run as Administrator, once per machine you install Face Unlock on.
#
#   .\tools\trust-signing-cert.ps1 -CerPath glancewin-signing.cer
#
# Imports the public certificate (no private key) into:
#   LocalMachine\Root             — so the signature chains to a trusted root
#   LocalMachine\TrustedPublisher — so SmartScreen and AV stop warning
#
# Undo with -Remove. Only ever do this for a certificate you created
# yourself: anything signed with it will be treated as trusted software.
param(
    [string]$CerPath = (Join-Path $env:USERPROFILE '.face-unlock\signing\glancewin-signing.cer'),
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'

$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Error "Run this from an Administrator PowerShell." }

if (-not (Test-Path $CerPath)) { Write-Error "Certificate not found: $CerPath" }
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $CerPath
if ($cert.HasPrivateKey) { Write-Error "$CerPath contains a private key - import the .cer, never the .pfx." }

Write-Host "Certificate: $($cert.Subject)"
Write-Host "Thumbprint : $($cert.Thumbprint)"

foreach ($store in 'Root', 'TrustedPublisher') {
    $path = "Cert:\LocalMachine\$store"
    $present = Get-ChildItem $path | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if ($Remove) {
        if ($present) { $present | Remove-Item -Force; Write-Host "  removed from $store" }
        else { Write-Host "  not in $store" }
        continue
    }
    if ($present) { Write-Host "  already in $store" }
    else {
        Import-Certificate -FilePath $CerPath -CertStoreLocation $path | Out-Null
        Write-Host "  imported into $store" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Verify a signed installer with:" -ForegroundColor Yellow
Write-Host "  Get-AuthenticodeSignature .\WindowsFaceUnlock-Setup-<ver>.exe | Format-List Status,SignerCertificate"
Write-Host "Status must read Valid."

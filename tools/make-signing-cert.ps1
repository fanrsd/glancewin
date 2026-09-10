# Create a self-signed code-signing certificate for this project.
#
#   .\tools\make-signing-cert.ps1
#
# Writes to %USERPROFILE%\.face-unlock\signing\ (never inside the repo):
#   glancewin-signing.pfx       private key — GitHub secret / local signing
#   glancewin-signing.cer       public cert — import on machines you install on
#   glancewin-signing.pwd.txt   the generated PFX password
#
# A self-signed certificate is trusted only where its public cert is
# imported (tools\trust-signing-cert.ps1). That is enough to silence
# SmartScreen and AV heuristics on your own machines, and worth nothing to
# anyone else — which is exactly the honest trust model here.
param(
    [string]$Subject = "CN=GlanceWin Face Unlock, O=fanrsd",
    [int]$Years = 5,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$outDir = Join-Path $env:USERPROFILE '.face-unlock\signing'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$pfx = Join-Path $outDir 'glancewin-signing.pfx'
$cer = Join-Path $outDir 'glancewin-signing.cer'
$pwdFile = Join-Path $outDir 'glancewin-signing.pwd.txt'

if ((Test-Path $pfx) -and -not $Force) {
    Write-Host "Already present: $pfx (use -Force to replace)" -ForegroundColor Yellow
    $existing = Get-PfxCertificate -FilePath $pfx
    Write-Host "  subject    : $($existing.Subject)"
    Write-Host "  thumbprint : $($existing.Thumbprint)"
    Write-Host "  expires    : $($existing.NotAfter)"
    return
}

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyAlgorithm RSA -KeyLength 3072 `
    -KeyUsage DigitalSignature `
    -CertStoreLocation Cert:\CurrentUser\My `
    -NotAfter (Get-Date).AddYears($Years)

# 24 random bytes, base64 — the password only guards the exported file.
$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$plain = [Convert]::ToBase64String($bytes)
$secure = ConvertTo-SecureString -String $plain -Force -AsPlainText

Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $secure | Out-Null
Export-Certificate  -Cert $cert -FilePath $cer -Type CERT | Out-Null
Set-Content -Path $pwdFile -Value $plain -NoNewline

Write-Host "Created code-signing certificate" -ForegroundColor Green
Write-Host "  subject    : $($cert.Subject)"
Write-Host "  thumbprint : $($cert.Thumbprint)"
Write-Host "  expires    : $($cert.NotAfter)"
Write-Host "  pfx        : $pfx"
Write-Host "  cer        : $cer"
Write-Host "  password   : $pwdFile"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1. Put it in GitHub Actions so releases are signed:"
Write-Host "     .\tools\push-signing-secrets.ps1"
Write-Host "  2. On every machine you install on (as Administrator):"
Write-Host "     .\tools\trust-signing-cert.ps1 -CerPath <copy of glancewin-signing.cer>"

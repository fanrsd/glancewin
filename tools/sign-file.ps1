# Sign a file with the project's code-signing certificate.
#
#   .\tools\sign-file.ps1 -Path installer_output\WindowsFaceUnlock-Setup-0.2.2.exe
#
# Uses the exported PFX by default; CI passes -PfxPath/-Password from secrets.
# The RFC-3161 timestamp keeps the signature valid after the certificate
# expires.
param(
    [Parameter(Mandatory)][string]$Path,
    [string]$PfxPath = (Join-Path $env:USERPROFILE '.face-unlock\signing\glancewin-signing.pfx'),
    [string]$Password,
    [string]$TimestampServer = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Path))    { Write-Error "File not found: $Path" }
if (-not (Test-Path $PfxPath)) { Write-Error "PFX not found: $PfxPath (run tools\make-signing-cert.ps1)" }

if (-not $Password) {
    $pwdFile = Join-Path (Split-Path -Parent $PfxPath) 'glancewin-signing.pwd.txt'
    if (-not (Test-Path $pwdFile)) { Write-Error "No -Password given and no $pwdFile" }
    $Password = (Get-Content $pwdFile -Raw).Trim()
}

# PowerShell 5.1's Get-PfxCertificate has no -Password parameter and prompts
# interactively for an encrypted PFX. Load it directly instead.
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 `
    @($PfxPath, $Password, 'Exportable,PersistKeySet')
if (-not $cert.HasPrivateKey) { Write-Error "PFX loaded without a private key" }

$result = Set-AuthenticodeSignature -FilePath $Path -Certificate $cert `
    -HashAlgorithm SHA256 -TimestampServer $TimestampServer

# Status is UnknownError on a machine that has not imported the public cert:
# the signature is present and intact, the root is simply not trusted there.
if ($result.Status -notin @('Valid', 'UnknownError')) {
    Write-Error "Signing failed: $($result.Status) - $($result.StatusMessage)"
}

$sig = Get-AuthenticodeSignature -FilePath $Path
Write-Host "Signed $Path" -ForegroundColor Green
Write-Host "  signer     : $($sig.SignerCertificate.Subject)"
Write-Host "  thumbprint : $($sig.SignerCertificate.Thumbprint)"
Write-Host "  timestamp  : $(if ($sig.TimeStamperCertificate) { $sig.TimeStamperCertificate.Subject } else { 'NONE' })"
Write-Host "  status     : $($sig.Status)  (UnknownError = untrusted root on this machine, expected)"

# Upload the code-signing PFX to GitHub Actions secrets, so tagged releases
# are signed automatically.
#
#   .\tools\push-signing-secrets.ps1
#
# Sets SIGNING_PFX_BASE64 and SIGNING_PFX_PASSWORD on the repo. The private
# key then lives in GitHub's secret store: fine for a self-signed personal
# certificate, not for a CA-issued one.
param(
    [string]$Repo = 'fanrsd/glancewin',
    [string]$PfxPath = (Join-Path $env:USERPROFILE '.face-unlock\signing\glancewin-signing.pfx'),
    [string]$PasswordFile = (Join-Path $env:USERPROFILE '.face-unlock\signing\glancewin-signing.pwd.txt')
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Write-Error "GitHub CLI (gh) not found." }
if (-not (Test-Path $PfxPath))      { Write-Error "PFX not found: $PfxPath (run tools\make-signing-cert.ps1)" }
if (-not (Test-Path $PasswordFile)) { Write-Error "Password file not found: $PasswordFile" }

$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($PfxPath))
$pw = (Get-Content $PasswordFile -Raw).Trim()

$b64 | & gh secret set SIGNING_PFX_BASE64 --repo $Repo
$pw  | & gh secret set SIGNING_PFX_PASSWORD --repo $Repo

Write-Host "Secrets set on $Repo" -ForegroundColor Green
& gh secret list --repo $Repo

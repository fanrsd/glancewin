# Set one scalar key in the live config, e.g.
#   .\tools\set_config.ps1 -Key verify_required -Value 2
# Appends the key if it is absent. Comments on the line are replaced.
param(
    [Parameter(Mandatory)][string]$Key,
    [Parameter(Mandatory)][string]$Value
)

$cfg = Join-Path $env:USERPROFILE '.face-unlock\config.toml'
if (-not (Test-Path $cfg)) { Write-Error "config not found: $cfg"; exit 1 }

$text = Get-Content $cfg -Raw
$line = "$Key = $Value"
$pattern = "(?m)^\s*$([regex]::Escape($Key))\s*=.*$"

if ($text -match $pattern) {
    $text = [regex]::Replace($text, $pattern, $line)
} else {
    $text = $text.TrimEnd() + "`r`n$line`r`n"
}

Set-Content -Path $cfg -Value $text -NoNewline
Get-Content $cfg | Select-String ([regex]::Escape($Key))

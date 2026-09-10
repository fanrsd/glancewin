# Toggle persistent_camera in the live config.
#   persistent_camera = true  -> webcam stays open, LED always on, verify ~0.1 s
#   persistent_camera = false -> webcam opened per request, LED blinks only then
param([ValidateSet('persistent','ondemand')][string]$Mode = 'ondemand')

$cfg = Join-Path $env:USERPROFILE '.face-unlock\config.toml'
if (-not (Test-Path $cfg)) { Write-Error "config not found: $cfg"; exit 1 }

$value = if ($Mode -eq 'persistent') { 'true' } else { 'false' }
$line = "persistent_camera = $value"
$text = Get-Content $cfg -Raw

if ($text -match '(?m)^\s*persistent_camera\s*=.*$') {
    $text = [regex]::Replace($text, '(?m)^\s*persistent_camera\s*=.*$', $line)
} else {
    $text = [regex]::Replace($text, '(?m)^(camera_index\s*=.*)$', "`$1`r`n$line")
}

Set-Content -Path $cfg -Value $text -NoNewline
Get-Content $cfg | Select-String 'camera_index|persistent_camera'
"Now run: .\.venv\Scripts\python -m tools.pipe_test reload_config"

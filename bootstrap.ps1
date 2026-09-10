# One-shot bootstrap for a machine with nothing installed.
#
#   Double-click install.cmd  (or: powershell -ExecutionPolicy Bypass -File bootstrap.ps1)
#
# 1. Finds a usable Python 3.10-3.13, installing 3.12 through winget if none.
# 2. Runs setup.ps1 (venv, dependencies, hash-pinned model download).
# 3. Opens the setup wizard, which handles enrollment, password, the service
#    task and the optional lock-screen tile.
#
# -CheckOnly reports what it would do and changes nothing.
param(
    [switch]$CheckOnly,
    [switch]$NoWizard
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$WINGET_ID = 'Python.Python.3.12'
$MIN = [version]'3.10'
$MAX_EXCL = [version]'3.14'   # 3.14 has no opencv-python wheel yet

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Get-PythonCandidates {
    $found = @()
    # `py -0p` lists every registered interpreter with its path.
    try {
        foreach ($line in (& py -0p 2>$null)) {
            if ($line -match '-V:(\d+\.\d+)\S*\s+\*?\s*(.+\\python\.exe)$') {
                $found += [pscustomobject]@{
                    Version = [version]$Matches[1]
                    Path    = $Matches[2].Trim()
                }
            }
        }
    } catch {}
    if (-not $found) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        # Skip the Microsoft Store execution alias: it resolves as a command
        # but only prints "Python was not found" and exits non-zero.
        if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') {
            try {
                $ErrorActionPreference = 'Continue'
                $v = (& $cmd.Source -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null |
                      Select-Object -First 1)
                if ($v -match '^\d+\.\d+$') {
                    $found += [pscustomobject]@{ Version = [version]$v; Path = $cmd.Source }
                }
            } catch {}
        }
    }
    # Newest usable version first.
    $found | Where-Object { $_.Version -ge $MIN -and $_.Version -lt $MAX_EXCL } |
        Sort-Object Version -Descending
}

function Install-Python {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Error @"
No Python 3.10-3.13 found and winget is unavailable.
Install Python 3.12 manually from https://www.python.org/downloads/windows/
(tick "Add python.exe to PATH"), then run this script again.
"@
    }
    Write-Step "Installing $WINGET_ID via winget (accept the prompt if one appears)"
    & winget install --id $WINGET_ID --exact --silent `
        --accept-package-agreements --accept-source-agreements
    # winget does not refresh this shell's PATH.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}

# --- 1. Python -------------------------------------------------------------
Write-Step "Looking for Python $MIN-3.13"
$candidates = Get-PythonCandidates
if ($candidates) {
    $python = $candidates[0]
    Write-Host "    found Python $($python.Version) at $($python.Path)"
} else {
    Write-Host "    none found" -ForegroundColor Yellow
    if ($CheckOnly) {
        $hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
        Write-Host "    would install $WINGET_ID via winget (winget present: $hasWinget)"
        return
    }
    Install-Python
    $candidates = Get-PythonCandidates
    if (-not $candidates) { Write-Error "Python still not found after install." }
    $python = $candidates[0]
    Write-Host "    installed Python $($python.Version) at $($python.Path)"
}

if ($CheckOnly) {
    # Either CMake's output dir or a DLL handed over from another machine.
    $dll = @(
        (Join-Path $root 'credential_provider\build\Release\FaceCredentialProvider.dll'),
        (Join-Path $root 'credential_provider\FaceCredentialProvider.dll')
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    Write-Host "    venv present : $(Test-Path (Join-Path $root '.venv'))"
    Write-Host "    models dir   : $(Test-Path (Join-Path $root 'models'))"
    Write-Host "    CP DLL       : $(if ($dll) { $dll } else { 'missing (optional: lock-screen tile)' })"
    Write-Host "CheckOnly: nothing was changed." -ForegroundColor Green
    return
}

# --- 2. venv + dependencies + models --------------------------------------
Write-Step "Creating the virtual environment and downloading models"
# -SkipAutostart: the wizard registers the service task, so the webcam LED
# stays off until you actually unlock (no presence probing by default).
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'setup.ps1') `
    -PythonExe $python.Path -SkipAutostart

# --- 3. Wizard -------------------------------------------------------------
if ($NoWizard) {
    Write-Host "Setup done. Run tools\wizard.cmd when you are ready." -ForegroundColor Green
    return
}
Write-Step "Opening the setup wizard"
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
Start-Process -FilePath $pyw -ArgumentList '-m', 'presence_monitor.wizard' -WorkingDirectory $root

Write-Host ""
Write-Host "The wizard is open. Work through the six steps." -ForegroundColor Green
Write-Host "Step 5 (lock-screen tile) needs credential_provider\build\Release\FaceCredentialProvider.dll:"
Write-Host "  copy it from a machine that already built it, or build it with Visual Studio + CMake."
Write-Host "Without it you still get the tray tools and walk-away locking; you sign in with your password."

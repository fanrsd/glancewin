# Answer one question: after a shutdown or restart, is the face-unlock tile
# still wired up, and what will actually happen at the first logon screen?
$clsid = '{F50C7625-CF2E-4572-A0CB-BCF578F9BECA}'

'== Credential Provider registration (machine-wide, survives reboot) =='
foreach ($hive in @('HKEY_LOCAL_MACHINE\SOFTWARE\Classes', 'HKEY_CURRENT_USER\Software\Classes')) {
    $k = "Registry::$hive\CLSID\$clsid\InprocServer32"
    if (Test-Path $k) { "  $hive : PRESENT -> $((Get-ItemProperty $k).'(default)')" }
    else { "  $hive : absent" }
}
$cp = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
"  LogonUI enable key   : $(if (Test-Path $cp) {'PRESENT'} else {'MISSING'})"

'== DLL the registration points at =='
$dll = if (Test-Path $cp) { (Get-ItemProperty "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CLSID\$clsid\InprocServer32" -ErrorAction SilentlyContinue).'(default)' }
if ($dll) {
    "  path   : $dll"
    "  exists : $(Test-Path $dll)"
    $drive = (Split-Path $dll -Qualifier)
    $d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$drive'"
    "  drive  : $drive DriveType=$($d.DriveType) (3 = fixed disk)"
    try {
        $bl = Get-BitLockerVolume -MountPoint $drive -ErrorAction Stop
        "  bitlocker: $($bl.ProtectionStatus) / $($bl.VolumeStatus)"
    } catch { "  bitlocker: not reported (feature absent or no permission)" }
}

'== Service autostart =='
$t = Get-ScheduledTask -TaskName 'FaceUnlock-Service' -ErrorAction SilentlyContinue
if ($t) {
    "  task   : present, State=$($t.State)"
    foreach ($tr in $t.Triggers) { "  trigger: $($tr.CimClass.CimClassName)" }
    "  runs as: $($t.Principal.UserId) LogonType=$($t.Principal.LogonType)"
} else { "  task   : MISSING - service will not start at logon" }

'== Stored secrets (DPAPI user scope) =='
$home_dir = Join-Path $env:USERPROFILE '.face-unlock'
foreach ($f in 'embeddings.npz', 'credentials.bin', 'config.toml') {
    $p = Join-Path $home_dir $f
    "  $f : $(if (Test-Path $p) {"$((Get-Item $p).Length) bytes"} else {'MISSING'})"
}

# Verify the Credential Provider is registered. regsvr32 /s hides failures,
# so check the two keys LogonUI actually reads.
$clsid = '{F50C7625-CF2E-4572-A0CB-BCF578F9BECA}'
$inproc = "Registry::HKEY_CLASSES_ROOT\CLSID\$clsid\InprocServer32"
$cpKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"

$ok = $true

if (Test-Path $inproc) {
    $p = (Get-ItemProperty $inproc).'(default)'
    $tm = (Get-ItemProperty $inproc).ThreadingModel
    "COM class  : OK  -> $p  (ThreadingModel=$tm)"
    if (-not (Test-Path $p)) { "  WARNING: DLL path does not exist"; $ok = $false }
} else {
    "COM class  : MISSING (HKCR\CLSID\$clsid\InprocServer32)"
    $ok = $false
}

if (Test-Path $cpKey) {
    "LogonUI    : OK  -> $((Get-ItemProperty $cpKey).'(default)')"
} else {
    "LogonUI    : MISSING (HKLM ...\Credential Providers\$clsid)"
    "             regsvr32 needs an elevated shell; /s swallowed the error."
    $ok = $false
}

if ($ok) { "`nRegistered. Lock with Win+L and pick the Face Unlock tile." ; exit 0 }
else { "`nNot fully registered." ; exit 1 }

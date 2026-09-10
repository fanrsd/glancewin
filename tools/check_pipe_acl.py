"""Assert the live named pipe is reachable only by this user and SYSTEM.

The pipe returns the plaintext Windows password on a face match. It used to
be created with a NULL DACL, which grants every local account access — so
this check reads the security descriptor off the *running* pipe, not off a
freshly built object, and fails if the restriction is missing.

    python -m tools.check_pipe_acl
"""

from __future__ import annotations

import sys

import win32api
import win32file
import win32security

PIPE_PATH = r"\\.\pipe\FaceUnlock"
SYSTEM_SID = "S-1-5-18"


def _own_sid() -> str:
    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32security.TOKEN_QUERY
    )
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        win32api.CloseHandle(token)
    return win32security.ConvertSidToStringSid(sid)


def main() -> int:
    # A pipe's security descriptor is only reachable through an open handle
    # and SE_KERNEL_OBJECT; GetNamedSecurityInfo/SE_FILE_OBJECT return
    # ERROR_INVALID_PARAMETER for pipe paths. READ_CONTROL alone is enough,
    # so this never sends a command.
    READ_CONTROL = 0x00020000
    try:
        handle = win32file.CreateFile(
            PIPE_PATH, READ_CONTROL, 0, None, win32file.OPEN_EXISTING, 0, None
        )
    except Exception as e:
        print(f"cannot open pipe: {e}")
        print("Is the service running? python -m tools.pipe_test ping")
        return 2
    try:
        sd = win32security.GetSecurityInfo(
            handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
    finally:
        handle.Close()

    dacl = sd.GetSecurityDescriptorDacl()
    if dacl is None:
        print("FAIL: NULL DACL - every local account can request your password")
        return 1

    allowed: list[str] = []
    for i in range(dacl.GetAceCount()):
        (ace_type, _flags), mask, sid = dacl.GetAce(i)
        s = win32security.ConvertSidToStringSid(sid)
        try:
            name, domain, _ = win32security.LookupAccountSid(None, sid)
            label = f"{domain}\\{name}"
        except Exception:
            label = s
        kind = "allow" if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE else f"type{ace_type}"
        print(f"  {kind} 0x{mask:08x}  {label}  ({s})")
        if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE:
            allowed.append(s)

    me = _own_sid()
    failures = []
    if me not in allowed:
        failures.append(f"this user ({me}) has no allow ACE — service cannot serve you")
    if SYSTEM_SID not in allowed:
        failures.append("SYSTEM has no allow ACE — the lock screen tile will fail")
    extra = [s for s in allowed if s not in (me, SYSTEM_SID)]
    if extra:
        failures.append(f"unexpected principals allowed: {extra}")

    if failures:
        print("\nFAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("\nOK: only this user and SYSTEM can talk to the pipe")
    return 0


if __name__ == "__main__":
    sys.exit(main())

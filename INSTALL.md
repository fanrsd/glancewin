# Face Unlock — Fresh Install Guide

This captures every lesson learned during the original setup so the next
install on a fresh machine is painless. Read top-to-bottom.

## 0. Prerequisites

| Requirement | Tested version | Install command |
|---|---|---|
| Windows 10/11 x64 | 11 Pro 26200 | — |
| Python 3.11 or 3.12 | 3.12.10 | `winget install Python.Python.3.12` |
| Git | any | `winget install Git.Git` |
| CMake | 4.3 | `winget install Kitware.CMake` |
| VS Build Tools 2022 (C++ workload + Win11 SDK) | 17.14 | see §4 |
| GitHub CLI (optional, for push) | 2.89 | `winget install GitHub.cli` |

## 1. Install on a machine with nothing on it

Copy this folder to the machine (zip, USB, `git clone`) and **double-click
`install.cmd`**. It runs `bootstrap.ps1`, which:

1. looks for Python 3.10–3.13 (`py -0p`, then `python`, ignoring the
   Microsoft Store execution alias, which resolves as a command but only
   prints "Python was not found");
2. installs Python 3.12 through `winget install Python.Python.3.12` if none
   was found — this is the only step that may raise a UAC prompt;
3. runs `setup.ps1`: venv, the 9 dependencies, and the hash-pinned models;
4. opens the setup wizard (§3) for enrollment, password, service task and
   the optional lock-screen tile.

```powershell
.\install.cmd                 # normal run
.\bootstrap.ps1 -CheckOnly    # report what it would do, change nothing
.\bootstrap.ps1 -NoWizard     # set up only, open the wizard later
```

Measured on a machine that already had Python: **13 s** for venv + 9
dependencies, models already cached. Requires an internet connection.

To get the lock-screen tile without installing Visual Studio on that
machine, copy `FaceCredentialProvider.dll` from a machine that built it into
`credential_provider\` (the flat path is checked as well as
`build\Release\`), then use wizard step 5. Also give that build its own GUID
in `credential_provider/guid.h` — two machines may share a CLSID, but two
*different* providers must not.

`requirements.txt` pulls: `opencv-python`, `numpy`, `pywin32`, `psutil`,
`pystray`, `Pillow`, `sv-ttk`, `tomli` (Python < 3.11 only), `tomli-w`. No ML
frameworks — recognition, detection and liveness all run through OpenCV.

`setup.ps1` passes `--use-feature=truststore` to pip so it uses the Windows
certificate store; pip's bundled certifi is stale in some builds and fails
the TLS handshake to PyPI.

### What is still not a single signed .exe

There *is* a one-click installer pipeline
(`installer/build.py` → PyInstaller + Inno Setup, wired to
`.github/workflows/release.yml` on a `v*` tag), but it is not the easy path
for a couple of personal machines:

- The frozen bundle is **227 MB** unpacked (82 MB of that is `cv2.pyd`),
  versus ~40 MB of models for the source install.
- Unsigned PyInstaller executables trip antivirus heuristics. On the
  development machine here, **McAfee deleted both `face_service.exe` and
  `face_unlock_tray.exe`** within seconds of the build finishing —
  `CreateProcess` returned "file contains a virus or potentially unwanted
  software" (error 225). Windows Defender's real-time protection was off, so
  this was the third-party AV. Expect SmartScreen prompts too.
- Shipping it therefore needs code signing. The release workflow already
  supports SignPath (free for open-source): set the `SIGNPATH_API_TOKEN`,
  `SIGNPATH_ORG_ID` and `SIGNPATH_PROJECT_SLUG` secrets and the tagged build
  is signed automatically. Without those secrets the workflow still publishes,
  just unsigned.

The auto-updater is off unless you point it at your own fork:
`FACE_UNLOCK_UPDATE_REPO=owner/repo`. It must not be left pointing at
upstream — upstream's installer carries the old DeepFace/torch stack and a
different Credential Provider CLSID, and would overwrite this build.

Per-machine steps that cannot be copied: enrollment (`embeddings.npz`) and
the stored password (`credentials.bin`) are DPAPI-encrypted for one user on
one machine, and `credential_provider/guid.h` should get a fresh GUID per
build you distribute.

## 2. Download the ONNX models

`setup.ps1` runs this for you; run it by hand after a fresh clone or if a
download was interrupted:

```powershell
.\.venv\Scripts\python installer\download_weights.py
```

Each file is verified against a pinned SHA-256 and re-downloaded if the
hash does not match:

| Model | File | Size |
|---|---|---|
| SFace recognizer (OpenCV Zoo) | `models/face_recognition_sface_2021dec.onnx` | 37 MB |
| MiniFASNetV2 liveness (Silent-Face-Anti-Spoofing) | `models/2.7_80x80_MiniFASNetV2.onnx` | 1.7 MB |
| YuNet detector (OpenCV Zoo) | `models/face_detection_yunet_2023mar.onnx` | 227 KB |

YuNet is also committed to the repo, so a `git clone` already has it. It is
in the download list because a repo copied *without* git (zip, robocopy)
would otherwise start with no detector at all.

## 3. Enrollment + password

From the tray control panel (`tools\gui.cmd`): **Enroll face…** for the
capture wizard, **Set Windows password…** for the credential dialog. The
dialog checks the password with `LogonUser` before storing it, so a typo
cannot leave the tile feeding bad credentials to LogonUI.

Equivalent CLI, if you prefer a console:

```powershell
.\.venv\Scripts\python -m tools.enroll capture --count 15
.\.venv\Scripts\python -m tools.set_password
```

Enrollment accepts images where a face is detectable; with 15 captures
expect ~9 usable. Re-run with `--count 20` if fewer than 6 make it.

`set_password` stores `{user, password, domain}` in
`%USERPROFILE%\.face-unlock\credentials.bin` encrypted with DPAPI (user
scope). Password never leaves your user profile.

## 4. Install Visual Studio Build Tools (only for the Credential Provider)

Skip this section if you only want presence auto-lock without real lock-screen
unlock.

```powershell
winget install Microsoft.VisualStudio.2022.BuildTools --silent --override `
  "--wait --quiet --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --includeRecommended"
```

About 6–8 GB. Takes 10–20 minutes depending on bandwidth.

## 5. Build + register the Credential Provider DLL

```powershell
cd credential_provider
cmake -B build -A x64 -G "Visual Studio 17 2022"
cmake --build build --config Release
# Then, from an Administrator PowerShell:
.\register.ps1 -Action register
```

Uninstall any time: `.\register.ps1 -Action unregister`.

### Gotchas encountered while building

These are already fixed in the source; listed only for troubleshooting.

1. **`FIELD_STATE_PAIR` undefined** — it's in the Microsoft sample set, not
   the public SDK. `helpers.h` defines it locally.
2. **`CPFG_CREDENTIAL_PROVIDER_LOGO` undefined** — same reason. We use
   `GUID_NULL` instead; the tile uses the default logo.
3. **`__ImageBase` undefined in `GetModuleFileNameW`** — because we call it
   directly from `DllRegisterServer`, not via a helper. Leave the
   `EXTERN_C IMAGE_DOS_HEADER __ImageBase;` at end of `dll.cpp`.
4. **`__try/__except` + C++ objects** — MSVC rejects it; use `try/catch`
   instead (already done).
5. **"Parameter is incorrect" from LogonUI** — two separate bugs:
   - `UNICODE_STRING.Buffer` inside the serialization must be an **offset**
     (in bytes from the start of the buffer), NOT an absolute pointer. LSA
     does the fixup across process boundaries.
   - Authentication package: use `"Negotiate"` (NEGOSSP_NAME_A), not
     `"Kerberos"`. Negotiate auto-picks Kerberos vs NTLM and works for
     local accounts. Do NOT fall through to `pkgId = 0` on lookup failure —
     return `HRESULT_FROM_NT(status)`.
6. **GUID must be unique** — replace `CLSID_FaceCredentialProvider` in
   `guid.h` with a freshly generated one (`uuidgen`) before distributing.

## 6. Runtime behaviour

### Config knobs (`%USERPROFILE%\.face-unlock\config.toml`)

| Key | Default | Notes |
|---|---|---|
| `threshold` | `0.55` | SFace cosine *distance* cutoff; lower = stricter. Measured on a UVC webcam, the same person lands at 0.09–0.30. |
| `anti_spoofing` | `true` | MiniFASNetV2 through `cv2.dnn`; no extra dependency |
| `camera_warmup_frames` | `10` | Helps dim lock-screen lighting |
| `persistent_camera` | `false` | `true` = ~0.9s verify, LED always on. `false` = ~3s verify, LED only while verifying. |
| `verify_frames` | `5` | Captured per unlock |
| `verify_required` | `2` | Matches needed |
| `presence_interval_s` | `60` | Presence auto-lock tick |
| `presence_absent_strikes` | `2` | Lock after N absent ticks |

### Services

Task Scheduler registers two logon tasks (created by `setup.ps1`):

- **FaceUnlock-Service** — the Python pipe server (`\\.\pipe\FaceUnlock`)
- **FaceUnlock-Presence** — the tray app + 60s camera probe

Restart both after editing config:

```powershell
powershell -ExecutionPolicy Bypass -File tools\clean_restart.ps1
```

### Environment variables that matter

Set in `face_service/__main__.py`. Only one is left now that the TF/torch
stack is gone — it caps OpenCV's DNN thread pool so those threads don't
compete with the pipe server during a verify:

```
OMP_NUM_THREADS=1
```

### Remote-session exclusion

`presence_monitor/remote_session.py` skips auto-lock when:

- RDP session is active (`GetSystemMetrics(SM_REMOTESESSION)`)
- Known remote-control process holds an ESTABLISHED external TCP connection
  (UltraViewer, AnyDesk, RustDesk, Parsec, Chrome Remote Desktop, Splashtop)
- Process name-only match for tools that only run during active sessions
  (TeamViewer_Desktop.exe, Quick Assist, MSRA)

Tune the list in that file if your remote tool is missing.

### Lock-screen auto-trigger

`FaceCredentialProvider::GetCredentialCount` returns
`pbAutoLogonWithDefault = TRUE` and `FaceCredential::SetSelected` returns
`pbAutoLogon = TRUE`. Result: as soon as the lock screen appears (key
press / mouse motion), the face tile is selected and verification runs
automatically.

Safety: `GetSerialization` has a hard 12-second timeout and returns
`S_FALSE` on failure, so a bad verify cannot lock the user out of the
password tile.

## 7. If you also have `facewinunlock-tauri` installed

Run the disable script once (as Administrator) to turn off its autostart,
kill its processes, and remove its Credential Provider registrations
(backed up first):

```powershell
tools\disable_tauri.ps1
```

Backup lives at `%USERPROFILE%\face-unlock-backup\` — `reg import` those
files to restore if needed.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot open camera index 0` | Close other camera apps; Teams/Zoom/UltraViewer can hold the device. Try `camera_index = 1`. |
| Enrollment says "No face found" on all images | Lighting too dim, or you weren't centred. Re-run `enroll capture --count 20`. |
| Verify is slow (>5s per call) | Models didn't pre-warm. Check `service.log` for "model warmup ok". Restart service. |
| Two `python.exe` processes for one service | Normal — venv launcher spawns the real interpreter. Only the inner one runs our code. |
| `Parameter is incorrect` on lock screen | You're running an old DLL. Re-run `cmake --build build --config Release` and lock/unlock once to reload. |
| Lock screen hangs for ~12 s | FaceService is down. `Start-ScheduledTask FaceUnlock-Service`. |
| User stuck, can't reach password | Click "Sign-in options" link on lock screen → pick Password tile. Or boot into Safe Mode; third-party CPs are disabled there. |

## 9. Logs

- `%USERPROFILE%\.face-unlock\service.log` — FaceService
- `%USERPROFILE%\.face-unlock\presence.log` — PresenceMonitor
- Event Viewer → Applications and Services Logs → Microsoft → Windows →
  User Profile Service / Authentication — for LogonUI / LSA errors when
  debugging Credential Provider issues

## 10. Uninstall completely

```powershell
# Admin PowerShell
.\credential_provider\register.ps1 -Action unregister
Unregister-ScheduledTask -TaskName 'FaceUnlock-Service' -Confirm:$false
Unregister-ScheduledTask -TaskName 'FaceUnlock-Presence' -Confirm:$false
Remove-Item -Recurse -Force "$env:USERPROFILE\.face-unlock"
Remove-Item -Recurse -Force .\.venv
```

The repo can then be deleted.

# Windows Face Unlock — face login + presence auto-lock for Windows 10/11

**An open-source Windows face recognition login and walk-away auto-lock —
the kind of "Howdy for Windows" / Windows Hello alternative that stays on
your machine, runs on any off-the-shelf webcam, and you can actually read
the source of.**

Keywords: *windows face unlock, windows face login, face recognition
windows, webcam login windows, howdy windows, windows hello alternative,
credential provider face, sface windows, onnx face recognition windows,
auto lock when away, presence monitor, walk-away lock, face id for pc.*

| | |
|---|---|
| Platform | Windows 10 / 11 x64 |
| Python   | 3.11 or 3.12 |
| License  | MIT |
| Models   | SFace + MiniFASNetV2 + YuNet — all ONNX, run through OpenCV |

## Features at a glance

- **Log in with your face** from the Windows lock screen via a proper
  Credential Provider tile (C++ DLL), not a user-mode hack.
- **Walk-away auto-lock**: every minute the tray process probes the webcam;
  if your enrolled face isn't there, `LockWorkStation()` fires.
- **Two presence modes**: strict (must match the enrolled face, blocks
  strangers) or lightweight (any face is enough, replaces old AutoFaceLock
  scripts).
- **Anti-spoofing** (liveness, MiniFASNetV2) blocks printed photos and
  photos or videos played on a screen.
- **Remote-session aware**: skips auto-lock when the session is RDP, or
  when TeamViewer / AnyDesk / RustDesk / Parsec / Chrome Remote Desktop /
  Quick Assist / UltraViewer hold an active remote connection.
- **Managed from the tray**: live status dashboard, settings editor,
  guided enrollment wizard with live camera preview + auto-capture, one
  Quit button that actually stops everything.
- **12-language UI** — English, Tiếng Việt, 中文, Español, Français,
  Deutsch, 日本語, 한국어, Русский, Português, العربية, हिन्दी. Switch
  from the tray, applies live.
- **DPAPI-encrypted** Windows password storage (user scope).

## Install (end user)

### Option A — installer (nothing pre-installed, not even Python)

Download `WindowsFaceUnlock-Setup-<ver>.exe` from the
[**Releases page**](https://github.com/fanrsd/glancewin/releases) and
double-click it: 87 MB, bundles Python, OpenCV, the three ONNX models and
the Credential Provider DLL, then starts the tray so you can run the wizard.

```powershell
(Get-FileHash .\WindowsFaceUnlock-Setup-0.2.2.exe -Algorithm SHA256).Hash
# compare with the .sha256 asset next to it
```

**Read this before choosing Option A.** Signed with a self-signed
certificate (see *Code signing policy*), which no machine trusts until you
import it — so SmartScreen still says *"unknown publisher"*: click
**More info → Run anyway**.

Worse, antivirus heuristics dislike unsigned PyInstaller executables.
Measured on a Windows 11 machine running McAfee: the installer ran fine and
laid down `face_service.exe` and `face_unlock_tray.exe`, and **within a
minute McAfee had deleted both executables and removed the two scheduled
tasks with them** — leaving an installed-but-dead app. Windows Defender
alone did not object. If your machine behaves like that, either import the
signing certificate first, add an exclusion for
`C:\Program Files\WindowsFaceUnlock`, or use Option B, which ships no frozen
executables at all (`python.exe` is signed by the Python Software
Foundation, so it is never the thing that gets quarantined).

### Option B — from source (no frozen binaries, no AV drama)

Copy this folder to the machine and **double-click `install.cmd`**. It finds
Python 3.10–3.13, installs Python 3.12 via `winget` if there is none, creates
the venv, downloads the hash-pinned ONNX models, and opens the setup wizard.
Measured at 13 s on a machine that already had Python.

```powershell
.\install.cmd                 # bootstrap + wizard
.\bootstrap.ps1 -CheckOnly    # preflight only, changes nothing
```

Either way the wizard walks six steps: models → enrollment → Windows
password → service task → lock-screen tile (optional, needs admin) → live
test. For Option B the tile needs `FaceCredentialProvider.dll`: build it
(Visual Studio + CMake, see [`credential_provider/README.md`](credential_provider/README.md))
or drop one built elsewhere into `credential_provider\`.

Update checks hit this repo's releases; set `FACE_UNLOCK_UPDATE_REPO=` (empty)
to switch them off, or point it at your own fork.

## Code signing policy

Releases from `v0.2.2` on are **Authenticode-signed with this project's own
self-signed certificate** (`CN=GlanceWin Face Unlock, O=fanrsd`,
thumbprint `F9670BAF0A346243C4AF46094FEEA44AA3242B1E`), RFC-3161 timestamped
so the signature outlives the certificate. The release job fails rather than
publishing an unsigned or untimestamped installer.

A self-signed certificate chains to no public CA, so **it is trusted only on
machines where you import it**. On each of your machines, from an
Administrator PowerShell:

```powershell
.\tools\trust-signing-cert.ps1 -CerPath .\glancewin-signing.cer
```

That imports the *public* certificate into `LocalMachine\Root` and
`LocalMachine\TrustedPublisher`; `Get-AuthenticodeSignature` on the installer
then reads `Valid` instead of `UnknownError`, and SmartScreen stops warning.
Undo with `-Remove`. Never import the `.pfx` — that is the private key.

Elsewhere the signature proves nothing, so verify by SHA-256; every release
ships a `.sha256` asset generated in the same run that built the installer:

```powershell
(Get-FileHash .\WindowsFaceUnlock-Setup-0.2.2.exe -Algorithm SHA256).Hash
```

Builds are produced only by
[`.github/workflows/release.yml`](.github/workflows/release.yml) on
GitHub-hosted runners from a `v*` tag; nothing is uploaded from a developer
machine. The signing key lives in the repository's Actions secrets
(`SIGNING_PFX_BASE64`, `SIGNING_PFX_PASSWORD`).

Not using SignPath Foundation: their conditions require a signed-fork chain
this project cannot show — the repo is not a GitHub fork of upstream, and
upstream publishes no signed builds. A publicly trusted signature would need
a paid certificate (e.g. Azure Trusted Signing).

Team roles: this is a single-maintainer project —
[fanrsd](https://github.com/fanrsd) is author, reviewer and release approver.

Privacy: the program transfers no information to other systems, with one
exception — the tray checks `api.github.com` for a newer release. Disable it
by setting `FACE_UNLOCK_UPDATE_REPO=` (empty). Your face embeddings and
Windows password never leave your machine: they live in
`%USERPROFILE%\.face-unlock\`, DPAPI-encrypted for your user account.

## Architecture

An open-source, auditable replacement for closed-source webcam-login utilities
(like `facewinunlock-tauri`). Three cooperating components:

| Component             | Language | Runs as                 | Role                                                                 |
|-----------------------|----------|-------------------------|----------------------------------------------------------------------|
| `face_service`        | Python   | User session (always)   | Camera + OpenCV SFace + liveness + DPAPI; exposes a named pipe.      |
| `presence_monitor`    | Python   | User session (tray)     | Every 60 s, probe presence; if absent → `LockWorkStation()`.         |
| `credential_provider` | C++      | LogonUI (SYSTEM)        | Windows Credential Provider tile that calls the service on unlock.   |

Plus two CLI tools: `tools.enroll` (capture reference photos) and
`tools.set_password` (store your Windows password encrypted with DPAPI).

## Why three pieces?

Windows lock-screen authentication runs in an isolated session as `SYSTEM`,
which cannot comfortably load OpenCV with its ONNX models / open the
webcam. The C++ Credential Provider is therefore a thin shim that
communicates with the heavyweight Python service over a local named pipe.
This is the same pattern Howdy uses on Linux with PAM.

## Features

- **SFace face recognition** (OpenCV's `cv2.FaceRecognizerSF`, 128-d
  embeddings) with cosine-distance thresholding — detect + embed + liveness
  runs in ~16 ms/frame on CPU (AMD Ryzen 7 7445HS)
- **Anti-spoofing (liveness)** via MiniFASNetV2 through `cv2.dnn` — blocks
  printed photos and photos or videos played on a screen
- **DPAPI-protected** Windows password storage (user scope)
- **Multi-frame voting** for unlock: N out of M frames must match
- **Presence auto-lock** every minute, with *remote-context exclusion*:
  skips when the session is RDP or when TeamViewer / AnyDesk / RustDesk /
  Parsec / Chrome Remote Desktop / Quick Assist / UltraViewer are actively
  connected. Also skips when input was received recently or when paused
  from the tray icon.
- **Two presence modes** (`presence_mode` in config):
  - `recognition` (default) — enrolled face must match (strong; walk-away +
    stranger detection).
  - `detection` — *any* face in frame is enough, via YuNet (weaker; replaces
    the old standalone AutoFaceLock script).
- **System tray management UI** (pystray + tkinter) — Status dashboard,
  Settings editor, Enroll / Set-password shortcuts, Pause/Resume, and a
  single Quit that stops both service and tray cleanly.

## Requirements

- Windows 10 / 11 x64
- Python 3.11 or 3.12
- Webcam
- (For Credential Provider) Visual Studio 2022 + CMake

## Install (Python parts)

```powershell
# From this folder, in PowerShell
.\setup.ps1
```

This creates `.\.venv`, installs dependencies, downloads the two
hash-pinned ONNX models that aren't tracked in git (SFace recognizer,
MiniFASNetV2 liveness) via `python installer/download_weights.py`, writes a
default config to `%USERPROFILE%\.face-unlock\config.toml`, and registers
Task Scheduler jobs that run `face_service` and `presence_monitor` at
logon. YuNet already ships in the repo.

## Enroll your face + store password

```powershell
.\.venv\Scripts\python -m tools.enroll capture --count 15
.\.venv\Scripts\python -m tools.set_password
```

Rebuild embeddings any time with:

```powershell
.\.venv\Scripts\python -m tools.enroll build
```

## (Optional) Enable the lock-screen tile

See [credential_provider/README.md](credential_provider/README.md). You will
need Visual Studio 2022. Without this, the presence-lock still works — you
just unlock with your password like usual.

## Quick test (no Credential Provider needed)

```powershell
# Terminal 1
.\.venv\Scripts\python -m face_service

# Terminal 2
.\.venv\Scripts\python -m presence_monitor
```

### Control panel without walk-away locking

`tools\gui.cmd` (double-click) or:

```powershell
.\.venv\Scripts\pythonw -m presence_monitor --no-presence
```

`--no-presence` starts the tray with presence probing paused, so the webcam
LED only lights while you unlock. Everything else is unchanged: Status,
Settings, Enroll face, Set Windows password, log folder, language. Hit
**Resume** in the tray menu to turn walk-away locking on for that session.

### Setup wizard

`tools\wizard.cmd`, or tray → **Setup wizard…**, or:

```powershell
.\.venv\Scripts\pythonw -m presence_monitor.wizard
```

Six numbered steps, each one probing its own state so the wizard doubles as
a repair tool: **Models** (download + SHA-256 verify) → **Your face**
(enrollment wizard, embedding count) → **Password** (verified with
`LogonUser` before storing) → **Autostart** (register + start the logon task)
→ **Lock screen** (register the Credential Provider DLL; raises the UAC
prompt itself) → **Test** (one real verify through the same pipe the lock
screen uses). The footer shows what is still missing.

All windows use the Sun Valley ttk theme and follow the Windows
light/dark setting (`AppsUseLightTheme`); override with
`apply_theme(root, "light"|"dark")` in `presence_monitor/theme.py`.

Trigger a manual unlock probe:

```powershell
# Named-pipe one-shot client from PowerShell
$p = New-Object IO.Pipes.NamedPipeClientStream('.', 'FaceUnlock', 'InOut')
$p.Connect(5000)
$w = New-Object IO.StreamWriter($p); $w.AutoFlush = $true
$r = New-Object IO.StreamReader($p)
$w.Write('{"cmd":"verify"}'); $p.WaitForPipeDrain()
$r.ReadToEnd()
```

## Configuration reference

See [config.example.toml](config.example.toml). Key knobs:

- `threshold` — SFace cosine *distance* cutoff (default 0.55). Lower =
  stricter; the same person measures 0.09–0.30 on a UVC webcam. Tune after
  enrolling.
- `verify_frames` / `verify_required` — multi-frame voting.
- `presence_interval_s` — how often to probe (default 60).
- `presence_absent_strikes` — lock after N consecutive absent ticks (default 2,
  so effective lock timeout is `interval * strikes` = 2 minutes).

## Security notes

Read these before trusting the CP for daily unlock:

1. The stored Windows password is encrypted with **DPAPI user-scope**. That
   protects it from other users and from offline disk inspection, but **not**
   from malware running as you. If your attacker model includes that, use a
   smart card or Windows Hello proper.
2. The pipe's DACL allows only the owning user and `SYSTEM` (`SYSTEM` is
   required — the Credential Provider runs inside LogonUI). Verify with
   `python -m tools.check_pipe_acl`.
3. Anti-spoofing blocks printed photos and photos or videos played on a
   screen, but **not 3-D masks**. Harsh backlight can also make it reject a
   real face.
4. The credential provider skeleton uses a hard-coded GUID from this repo —
   **generate your own** before sharing builds.

## Credits / prior art

This project draws on ideas from:

- [boltgolt/howdy](https://github.com/boltgolt/howdy) — Linux/PAM face login
- [OpenCV Zoo](https://github.com/opencv/opencv_zoo) — YuNet detector +
  SFace recognizer (ONNX)
- [minivision-ai/Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing)
  — MiniFASNetV2 liveness weights
- [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) — dlib wrapper
- Microsoft's [SampleCredentialProvider](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/CredentialProvider)
  — reference implementation for `ICredentialProvider`

## Contributing

Issues and PRs are welcome. Before sending a PR please:

- Run `python -m tools.bench` if you touched the recognizer / camera paths.
- Keep new UI strings translatable — add keys to
  [`face_service/i18n.py`](face_service/i18n.py) under all 12 languages
  (English fallback is automatic if a key is missing).
- Generate your own GUID in `credential_provider/guid.h` if you're going
  to register the CP DLL on your machine.

## License

MIT — see [LICENSE](LICENSE).

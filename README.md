# F.R.I.D.A.Y Command Center

**F.R.I.D.A.Y Command Center** is a local Windows desktop AI command interface with a holographic command-center UI, Gemini voice interaction, text commands, file analysis, local desktop actions, and optional MEDPOV Security Center integration.

Designed by **MEDPOV**.

## Interface Preview

F.R.I.D.A.Y Command Center includes multiple visual modes, Security Center integration panels, live map views, API configuration screens, responsive layouts, and camera-assisted desktop interaction.

<p align="center">
  <img src="assets/readme/1.png" alt="F.R.I.D.A.Y Command Center Active Mode" width="900">
</p>

### Visual Modes

<p align="center">
  <img src="assets/readme/1.png" alt="Green Active Mode" width="31%">
  <img src="assets/readme/2.png" alt="Orange Listening Mode" width="31%">
  <img src="assets/readme/3.png" alt="Red Alert Mode" width="31%">
</p>

### Security Center Integration

<p align="center">
  <img src="assets/readme/5.png" alt="Security Map View" width="48%">
  <img src="assets/readme/6.png" alt="Security Center Data View" width="48%">
</p>

### Settings, Responsive UI and Camera Mode

<p align="center">
  <img src="assets/readme/4.png" alt="Settings Panel" width="31%">
  <img src="assets/readme/8.png" alt="Responsive Layout" width="31%">
  <img src="assets/readme/9.png" alt="Camera Developer Desktop" width="31%">
</p>

> F.R.I.D.A.Y runs on the user’s own Windows computer. WAMP is **not required**. The recommended installation path is `C:\MEDPOV\security-center-f.r.i.d.a.y-ai`.

F.R.I.D.A.Y is designed to work in parallel with the **MEDPOV Security Center** software. When connected to a Security Center installation, it can help monitor security events, review threat summaries, analyze suspicious IP addresses, and provide voice or text-based operational assistance from the local desktop interface.

Learn more about MEDPOV Security Center:  
https://medpov.com/product/medpov-security-center

---

## Quick Windows Installation

For most Windows users, use this installation method.

Open **PowerShell** and run:

```powershell
cd C:\
mkdir MEDPOV
cd C:\MEDPOV
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
.\install_friday.bat
```

The installer will:

| Step | What Happens |
|---|---|
| 1 | Creates or uses the local `.venv` Python environment. |
| 2 | Installs all required Python packages into `.venv`. |
| 3 | Installs Playwright Chromium. |
| 4 | Creates local configuration files. |
| 5 | Creates a desktop shortcut named `FRIDAY AI`. |
| 6 | Uses `assets/friday.ico` as the shortcut icon when available. |

After setup finishes, start F.R.I.D.A.Y from the desktop shortcut:

```text
FRIDAY AI
```

Or start it manually:

```powershell
.\start_friday.ps1
```

If PowerShell blocks the script, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_friday.ps1
```

On first launch, F.R.I.D.A.Y will ask for your Gemini API key inside the interface.  
The key will be saved automatically to:

```text
config/api_keys.json
config/friday_settings.json
```

Security Center connection is optional and can be configured later from **FRIDAY SETTINGS**.

---

## Important Installation Note

Do **not** run this after creating `.venv`:

```powershell
python setup.py
```

This may use the global Python installation instead of the project virtual environment.

Use one of these instead:

```powershell
.\install_friday.bat
```

or:

```powershell
.\.venv\Scripts\python.exe setup.py
```

The correct setup output should show paths like:

```text
C:\MEDPOV\security-center-f.r.i.d.a.y-ai\.venv\Scripts\python.exe
```

If the output shows a path like this:

```text
C:\Users\YourUser\AppData\Local\Programs\Python\Python312\python.exe
```

then setup is running outside `.venv`.

---

## What This Application Does

| Area | Description |
|---|---|
| Desktop AI Interface | Provides a local Windows command-center UI for F.R.I.D.A.Y. |
| Voice Mode | Uses Gemini Live API for voice-based interaction. |
| Text Commands | Supports written commands from the direct command input area. |
| File Analysis | Allows supported files, images, documents, data files, and code files to be analyzed from the UI. |
| Local Actions | Can run supported local desktop, browser, file, and system helper actions. |
| Security Center Integration | Can connect to a remote MEDPOV Security Center installation such as `https://siteadi.com/security-center`. |
| Settings Panel | Lets the user update Gemini API, voice profile, Security Center URL, and Security Center API key from the UI. |
| Desktop Shortcut | Creates a `FRIDAY AI` desktop shortcut for easy launching. |

---

## Required Software

Install these before running F.R.I.D.A.Y.

| Requirement | Required | Notes |
|---|---:|---|
| Windows 10 / Windows 11 | Yes | Recommended operating system. |
| Python 3.11+ | Yes | During installation, enable **Add Python to PATH**. Python 3.12 is supported. |
| Git for Windows | Yes | Required to clone the repository. |
| Gemini API Key | Yes | Required for Gemini Live voice and AI mode. |
| Microphone Access | Yes | Required for voice mode. |
| Internet Connection | Yes | Required for Gemini API and optional web actions. |
| Security Center URL/API Key | Optional | Can be configured later from FRIDAY SETTINGS. |
| Visual C++ Build Tools | Optional | Only needed if a Python package fails to install from a prebuilt wheel on a specific PC. |

---

## Recommended Folder Structure

F.R.I.D.A.Y does **not** need to be installed under WAMP or a web server folder.

Recommended location:

```text
C:\MEDPOV\security-center-f.r.i.d.a.y-ai
```

Recommended desktop shortcut:

```text
FRIDAY AI
```

Recommended icon path:

```text
assets\friday.ico
```

---

## Installation with PowerShell

Open **PowerShell** and run the commands below.

### Step 1 — Create the MEDPOV folder

```powershell
cd C:\
mkdir MEDPOV
cd C:\MEDPOV
```

### Step 2 — Clone the repository

```powershell
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
```

### Step 3 — Run the installer

```powershell
.\install_friday.bat
```

The installer creates `.venv`, installs packages into `.venv`, prepares config files, installs Playwright Chromium, and creates the desktop shortcut.

### Step 4 — Start F.R.I.D.A.Y

Double click the desktop shortcut:

```text
FRIDAY AI
```

Or run:

```powershell
.\start_friday.ps1
```

If PowerShell blocks the script:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_friday.ps1
```

---

## Clean Reinstall

If the folder already exists and you want a clean reinstall:

```powershell
cd C:\MEDPOV
Remove-Item .\security-center-f.r.i.d.a.y-ai -Recurse -Force
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
.\install_friday.bat
```

Then start from the desktop shortcut:

```text
FRIDAY AI
```

---

## Installation with CMD

Open **Command Prompt (CMD)** and run:

```cmd
cd /d C:\
mkdir MEDPOV
cd /d C:\MEDPOV
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
install_friday.bat
```

Start F.R.I.D.A.Y:

```cmd
start_friday.bat
```

---

## Manual Advanced Installation

Use this only if you do not want to use `install_friday.bat`.

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
python -m venv .venv
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe main.py
```

Do not use global `python setup.py` unless the virtual environment is activated correctly.

---

## 🔄 Update

To upgrade to the latest version, run the following steps:

### Step 1 — Go to project folder

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
```

### Step 2 — Pull latest code (hard reset)

```powershell
git fetch origin
git reset --hard origin/main
git clean -fd
```

### Step 3 — Activate virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 4 — Update dependencies

```powershell
pip install -r requirements.txt
pip install opencv-python
```

---

### ⚡ Quick Update (One command)

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
git fetch origin
git reset --hard origin/main
git clean -fd
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install opencv-python
```

---

### 🚀 Start after update

```powershell
.\start_friday.ps1
```

---

## First Launch Configuration

F.R.I.D.A.Y does not ask for the Gemini API key during setup.

On first launch:

1. F.R.I.D.A.Y opens the setup overlay.
2. Enter your Gemini API key.
3. Confirm the detected operating system.
4. Click **ACTIVATE FRIDAY CORE**.
5. F.R.I.D.A.Y saves the key and starts the local AI command interface.

The API key is saved into both files:

| File | Purpose | Git Status |
|---|---|---|
| `config/api_keys.json` | Local Gemini API key and compatibility config. | Ignored by Git |
| `config/friday_settings.json` | Main FRIDAY settings store. | Ignored by Git |
| `config/security_center.json` | Optional Security Center URL/API key. | Ignored by Git |
| `config/friday_wake.json` | Local standby/wake behavior settings. | Ignored by Git |
| `config/*.example.json` | Safe example configuration files. | Committed to Git |

Expected `config/api_keys.json` shape:

```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "google_api_key": "YOUR_GEMINI_API_KEY",
  "GOOGLE_API_KEY": "YOUR_GEMINI_API_KEY",
  "os_system": "windows",
  "friday_voice_name": "Aoede",
  "friday_voice_language": "tr-TR",
  "friday_voice_profile": "female_soft",
  "friday_character_gender": "female",
  "gemini_live_model": "gemini-2.5-flash-native-audio-preview-12-2025"
}
```

Expected `config/friday_settings.json` shape:

```json
{
  "voice": {
    "name": "Aoede",
    "language": "tr-TR",
    "character_gender": "female"
  },
  "security_center": {
    "base_url": "https://siteadi.com/security-center",
    "api_url": "https://siteadi.com/security-center/admin/api/remote-access.php",
    "api_key": "",
    "timeout": 25
  },
  "gemini": {
    "api_key": "YOUR_GEMINI_API_KEY",
    "model": "gemini-2.5-flash-native-audio-preview-12-2025"
  }
}
```

---

## FRIDAY Settings Panel

After the application opens, use **FRIDAY SETTINGS** to update important settings without editing code.

| Setting | Description |
|---|---|
| Voice Profile | Choose female or male voice profiles. |
| Voice Language | Set the voice language code, for example `tr-TR`. |
| Gemini API Key | Update the Gemini API key. |
| Gemini Model | Update the Gemini Live model if needed. |
| Security Center Base URL | Example: `https://siteadi.com/security-center`. |
| Security Center API Key | API key generated by the Security Center installation. |

After changing Gemini voice, model, or API settings, restart F.R.I.D.A.Y.

---

## Security Center Integration

Security Center integration is optional. F.R.I.D.A.Y can run without it.

To connect it later:

1. Start F.R.I.D.A.Y.
2. Open **FRIDAY SETTINGS**.
3. Open the **Security Center** tab.
4. Enter the base URL:

```text
https://siteadi.com/security-center
```

5. Enter the Security Center API key.
6. Save settings.
7. Restart F.R.I.D.A.Y.

F.R.I.D.A.Y automatically uses this API path:

```text
/admin/api/remote-access.php
```

Full endpoint example:

```text
https://siteadi.com/security-center/admin/api/remote-access.php
```

Supported Security Center actions may include:

| Action | Description |
|---|---|
| Overview | Shows Security Center summary. |
| Latest Threats | Lists recent high-risk events. |
| Health | Checks Security Center API status. |
| Live Sessions | Shows active live sessions when available. |
| IP Profile | Shows security history for an IP address. |
| IP Analysis | Analyzes an IP or event. |
| IP Block | Sends a block request to Security Center. |
| Resolve Event | Marks an event as resolved when supported. |

---

## Voice Profiles

Example female voice profiles:

| Voice | Style |
|---|---|
| Aoede | Soft / balanced |
| Leda | Net / clear |
| Kore | Balanced |
| Zephyr | Light |
| Callirrhoe | Premium |
| Autonoe | Calm |

Example male voice profiles:

| Voice | Style |
|---|---|
| Puck | Energetic |
| Charon | Deep |
| Fenrir | Strong |
| Orus | Professional |
| Iapetus | Deep |
| Umbriel | Dark |
| Algieba | Balanced |

Restart F.R.I.D.A.Y after changing the voice profile.

---

## Updating the Application

### Recommended update method

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
git pull
.\install_friday.bat
```

Then start:

```powershell
.\start_friday.ps1
```

or double click:

```text
FRIDAY AI
```

### Manual update method

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe main.py
```

---

## Desktop Shortcut and Icon

The installer creates this shortcut:

```text
Desktop\FRIDAY AI.lnk
```

The shortcut starts:

```text
start_friday.bat
```

For a custom icon, place the icon here:

```text
assets\friday.ico
```

The setup script will use this icon automatically when creating the desktop shortcut.

Recommended icon source file:

```text
assets\friday.png
```

Convert it to `.ico` using:

```powershell
.\.venv\Scripts\python.exe tools\make_friday_icon.py
```

Then run setup again:

```powershell
.\.venv\Scripts\python.exe setup.py
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| `python is not recognized` | Python is not installed or not added to PATH. | Reinstall Python and enable **Add Python to PATH**. |
| `git is not recognized` | Git is not installed or not added to PATH. | Install Git for Windows and reopen the terminal. |
| `ModuleNotFoundError: No module named 'sounddevice'` | Packages were installed into global Python instead of `.venv`. | Run `.\.venv\Scripts\python.exe setup.py`. |
| `destination path already exists` | The clone folder already exists. | Delete the old folder or clone into a different folder name. |
| PowerShell blocks `.ps1` | Windows execution policy. | Use `powershell -ExecutionPolicy Bypass -File .\start_friday.ps1`. |
| Microphone does not work | Windows microphone permission is disabled. | Enable microphone access from Windows Privacy settings. |
| Gemini setup appears again | API key is missing in config files. | Enter the key in the first-launch setup overlay or FRIDAY SETTINGS. |
| Gemini connection error | API key/model is missing or invalid. | Check Gemini API key and model in FRIDAY SETTINGS. |
| Security Center shows offline | Security Center URL/API key is missing or still using placeholder values. | Configure Security Center from FRIDAY SETTINGS. |
| Package installation fails | Missing build tools or old pip. | Run `.\.venv\Scripts\python.exe -m pip install --upgrade pip`; install Visual C++ Build Tools if required. |
| Desktop icon looks generic | `assets/friday.ico` is missing. | Add `assets/friday.png`, run `tools\make_friday_icon.py`, then run setup again. |

---

## Git Safety Notes for Developers

Do **not** commit these runtime/private files:

```text
config/api_keys.json
config/friday_settings.json
config/security_center.json
config/friday_wake.json
memory/
logs/
.venv/
__pycache__/
*.pyc
```

Only commit safe example config files:

```text
config/api_keys.example.json
config/friday_settings.example.json
config/security_center.example.json
config/friday_wake.example.json
```

Commit the desktop icon assets:

```text
assets/friday.png
assets/friday.ico
```

---

## Project Structure

```text
actions/        Local command/action modules
agent/          Agent planning and execution logic
assets/         Desktop icon and visual assets
config/         Local config examples and runtime config files
core/           Prompt and core assistant instructions
memory/         Local runtime memory, ignored by Git
tools/          Settings, Security Center client, icon helper, and helper tools
main.py         Main application entry point
ui.py           PyQt6 desktop interface
setup.py        Installation and first-run setup helper
requirements.txt
README.md
```

---

## Credits

F.R.I.D.A.Y Command Center was designed by **MEDPOV**.

MEDPOV Security Center product page:  
https://medpov.com/product/medpov-security-center

## v2.7.0 Multi AI Provider

FRIDAY v2.7.0 ile Gemini yanında OpenAI provider desteği eklenmiştir. Ayarlar panelinden `Gemini`, `OpenAI` veya `Auto / Fallback` seçilebilir. OpenAI modu yazılı komut routing, kamera/görüntü analizi ve dosya AI işlemlerini OpenAI üzerinden çalıştırabilir. Mevcut Gemini Live bağlantısı ses/transkripsiyon köprüsü ve eski davranış için korunur.

OpenAI kullanmak için:

1. `pip install -r requirements.txt`
2. FRIDAY > Ayarlar > OpenAI sekmesine API key gir.
3. OpenAI bağlantısını test et.
4. AI Provider sekmesinden OpenAI veya Auto / Fallback seç.
5. Kaydet ve uygulamayı yeniden başlat.

## v2.7.1 OpenAI Natural Voice

FRIDAY v2.7.1, OpenAI provider modundaki robotik Windows lokal TTS davranışını kaldırır. OpenAI üzerinden üretilen yazılı komut ve kamera/vision cevapları artık `gpt-4o-mini-tts` tabanlı doğal ses çıktısı ile okunabilir.

### Eklenenler

- OpenAI Provider modunda doğal OpenAI TTS ses çıkışı
- OpenAI ayarlarına `TTS model` alanı
- OpenAI voice seçimi: `marin`, `cedar`, `coral`, `nova`, `shimmer`, `alloy`, `ash`, `ballad`, `echo`, `fable`, `onyx`, `sage`, `verse`
- Windows SAPI sadece yedek/offline fallback olarak bırakıldı
- Yeni cevap geldiğinde eski TTS akışını kesen latest-wins ses token sistemi
- Footer sürüm etiketi v2.7.1

> Not: v2.7.1 ses çıkışını doğal hale getirir. Mikrofon transkripsiyon köprüsü hâlâ Gemini Live üzerinden çalışır. Tam OpenAI speech-to-speech deneyimi için sonraki ana sürümde OpenAI Realtime provider ayrı olarak bağlanmalıdır.

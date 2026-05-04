# F.R.I.D.A.Y Command Center

**F.R.I.D.A.Y Command Center** is a local Windows desktop AI command interface with a holographic command-center UI, voice interaction, text commands, file analysis, local desktop actions, and optional Security Center integration.

Designed by **MEDPOV**.

> F.R.I.D.A.Y runs on the user’s own Windows computer. WAMP is **not required**. The recommended installation path is `C:\MEDPOV\security-center-f.r.i.d.a.y-ai`.

F.R.I.D.A.Y is designed to work in parallel with the **MEDPOV Security Center** software. When connected to a Security Center installation, it can help monitor security events, review threat summaries, analyze suspicious IP addresses, and provide voice or text-based operational assistance from the local desktop interface.

Learn more about MEDPOV Security Center:  
https://medpov.com/product/medpov-security-center
---

## 1. What This Application Does

| Area | Description |
|---|---|
| Desktop AI Interface | Provides a local Windows command-center UI for F.R.I.D.A.Y. |
| Voice Mode | Uses Gemini Live API for voice-based interaction. |
| Text Commands | Supports written commands from the command input area. |
| File Analysis | Allows supported files/images/documents to be analyzed from the UI. |
| Local Actions | Can run supported local desktop, browser, file, and system helper actions. |
| Security Center Integration | Can connect to a remote Security Center installation such as `https://siteadi.com/security-center`. |
| Settings Panel | Lets the user update Gemini API, voice profile, Security Center URL, and Security Center API key from the UI. |

---

## 2. Required Software

Install these before running F.R.I.D.A.Y.

| Requirement | Required | Notes |
|---|---:|---|
| Windows 10 / Windows 11 | Yes | Recommended operating system. |
| Python 3.11+ | Yes | During installation, enable **Add Python to PATH**. Python 3.12 is also supported. |
| Git for Windows | Yes | Required to clone the repository. |
| Gemini API Key | Yes | Required for Gemini Live voice/AI mode. |
| Microphone Access | Yes | Required for voice mode. |
| Internet Connection | Yes | Required for Gemini API and optional web actions. |
| Security Center URL/API Key | Optional | Can be configured later from the F.R.I.D.A.Y settings panel. |
| Visual C++ Build Tools | Optional | Only needed if a Python package fails to install from wheel on a specific PC. |

---

## 3. Recommended Folder Structure

F.R.I.D.A.Y does **not** need to be installed under WAMP or a web server folder.

Recommended location:

```text
C:\MEDPOV\security-center-f.r.i.d.a.y-ai
```

Example Security Center URL format:

```text
https://siteadi.com/security-center
```

F.R.I.D.A.Y automatically uses this API path:

```text
/admin/api/remote-access.php
```

Full endpoint example:

```text
https://siteadi.com/security-center/admin/api/remote-access.php
```

---

## 4. Installation with PowerShell

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

If the folder already exists and you want a clean reinstall:

```powershell
cd C:\MEDPOV
Remove-Item .\security-center-f.r.i.d.a.y-ai -Recurse -Force
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
```

### Step 3 — Create a Python virtual environment

```powershell
python -m venv .venv
```

### Step 4 — Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use this one-time bypass command:

```powershell
powershell -ExecutionPolicy Bypass -NoProfile
```

Then run again:

```powershell
.\.venv\Scripts\Activate.ps1
```

You can also skip activation and run Python directly like this:

```powershell
.\.venv\Scripts\python.exe --version
```

### Step 5 — Run setup

```powershell
python setup.py
```

During setup, enter your Gemini API key when requested.

### Step 6 — Start F.R.I.D.A.Y

```powershell
python main.py
```

If you did not activate the virtual environment, start it like this:

```powershell
.\.venv\Scripts\python.exe main.py
```

---

## 5. Installation with CMD

Open **Command Prompt (CMD)** and run the commands below.

### Step 1 — Create the MEDPOV folder

```cmd
cd /d C:\
mkdir MEDPOV
cd /d C:\MEDPOV
```

### Step 2 — Clone the repository

```cmd
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
```

If the folder already exists and you want a clean reinstall:

```cmd
cd /d C:\MEDPOV
rmdir /s /q security-center-f.r.i.d.a.y-ai
git clone https://github.com/elmasoral/security-center-f.r.i.d.a.y-ai.git
cd security-center-f.r.i.d.a.y-ai
```

### Step 3 — Create a Python virtual environment

```cmd
python -m venv .venv
```

### Step 4 — Activate the virtual environment

```cmd
.venv\Scripts\activate.bat
```

### Step 5 — Run setup

```cmd
python setup.py
```

During setup, enter your Gemini API key when requested.

### Step 6 — Start F.R.I.D.A.Y

```cmd
python main.py
```

---

## 6. First Launch Configuration

On first setup, F.R.I.D.A.Y creates local configuration files inside the `config` folder.

| File | Purpose | Git Status |
|---|---|---|
| `config/api_keys.json` | Local Gemini API key and model settings. | Ignored by Git |
| `config/friday_settings.json` | Local F.R.I.D.A.Y UI/settings preferences. | Ignored by Git |
| `config/security_center.json` | Local Security Center URL/API key. | Ignored by Git |
| `config/friday_wake.json` | Local standby/wake behavior settings. | Ignored by Git |
| `config/*.example.json` | Safe example configuration files. | Committed to Git |

If setup does not create the files automatically, copy the example files manually:

### PowerShell

```powershell
Copy-Item .\config\api_keys.example.json .\config\api_keys.json
Copy-Item .\config\friday_settings.example.json .\config\friday_settings.json
Copy-Item .\config\security_center.example.json .\config\security_center.json
Copy-Item .\config\friday_wake.example.json .\config\friday_wake.json
```

### CMD

```cmd
copy config\api_keys.example.json config\api_keys.json
copy config\friday_settings.example.json config\friday_settings.json
copy config\security_center.example.json config\security_center.json
copy config\friday_wake.example.json config\friday_wake.json
```

Then open `config/api_keys.json` and enter your Gemini API key.

Example:

```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "google_api_key": "YOUR_GEMINI_API_KEY",
  "friday_voice_name": "Aoede",
  "friday_voice_language": "tr-TR",
  "friday_voice_profile": "female_soft",
  "friday_character_gender": "female",
  "gemini_live_model": "gemini-2.5-flash-native-audio-preview-12-2025"
}
```

---

## 7. F.R.I.D.A.Y Settings Panel

After the application opens, use the **FRIDAY SETTINGS** panel to update important settings without editing code.

| Setting | Description |
|---|---|
| Voice Profile | Choose female or male voice profiles. |
| Voice Language | Set the voice language code, for example `tr-TR`. |
| Gemini API Key | Update the Gemini API key. |
| Gemini Model | Update the Gemini Live model if needed. |
| Security Center Base URL | Example: `https://siteadi.com/security-center`. |
| Security Center API Key | API key generated by the Security Center installation. |

After changing Gemini voice/model/API settings, restart F.R.I.D.A.Y.

---

## 8. Security Center Integration

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

## 9. Voice Profiles

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

## 10. Updating the Application

### PowerShell

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python setup.py
python main.py
```

### CMD

```cmd
cd /d C:\MEDPOV\security-center-f.r.i.d.a.y-ai
git pull
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python setup.py
python main.py
```

---

## 11. Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| `python is not recognized` | Python is not installed or not added to PATH. | Reinstall Python and enable **Add Python to PATH**. |
| `git is not recognized` | Git is not installed or not added to PATH. | Install Git for Windows and reopen the terminal. |
| `destination path already exists` | The clone folder already exists. | Delete the old folder or clone into a different folder name. |
| PowerShell blocks `.ps1` activation | Windows execution policy. | Use `powershell -ExecutionPolicy Bypass -NoProfile` or run `.venv\Scripts\python.exe` directly. |
| Microphone does not work | Windows microphone permission is disabled. | Enable microphone access from Windows Privacy settings. |
| Gemini connection error | API key/model is missing or invalid. | Check Gemini API key and model in FRIDAY SETTINGS. |
| Security Center unauthorized | Security Center API key is missing or invalid. | Update Security Center API key from FRIDAY SETTINGS. |
| Package installation fails | Missing build tools or old pip. | Run `python -m pip install --upgrade pip`; install Visual C++ Build Tools if required. |

---

## 12. Git Safety Notes for Developers

Do **not** commit these files:

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

Only commit the safe example config files:

```text
config/api_keys.example.json
config/friday_settings.example.json
config/security_center.example.json
config/friday_wake.example.json
```

---

## 13. Project Structure

```text
actions/        Local command/action modules
agent/          Agent planning and execution logic
config/         Local config examples and runtime config files
core/           Prompt and core assistant instructions
memory/         Local runtime memory, ignored by Git
tools/          Settings, Security Center client, and helper tools
main.py         Main application entry point
ui.py           PyQt6 desktop interface
setup.py        Installation and first-run setup helper
requirements.txt
README.md
```

---

## 14. Credits

F.R.I.D.A.Y Command Center was designed by **MEDPOV**.


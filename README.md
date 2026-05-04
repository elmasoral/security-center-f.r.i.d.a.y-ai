# F.R.I.D.A.Y Command Center

F.R.I.D.A.Y Command Center is a local Windows desktop AI command interface. It provides a holographic command-center UI, Gemini Live voice interaction, text commands, file analysis, local desktop actions, and optional Security Center integration.

Designed by **MEDPOV**.

---

## Features

- Local desktop AI command center
- Gemini Live voice interaction
- Female and male voice selection
- Text command input
- File analysis panel
- Standby, listening, and mute visual modes
- Animated F.R.I.D.A.Y circular command core
- Optional Security Center remote integration
- Editable Gemini and Security Center settings from the UI

---

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer
- Microphone access
- Internet connection
- Gemini API key
- Optional Security Center installation, for example:

```text
https://siteadi.com/security-center
```

---

## Installation

Clone the repository:

```powershell
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Run the setup:

```powershell
python setup.py
```

The setup installs dependencies and asks for your Gemini API key.

---

## Start F.R.I.D.A.Y

```powershell
python main.py
```

---

## First Configuration

During setup, enter your Gemini API key.

If you need to configure it manually, copy the example config:

```powershell
Copy-Item .\config\api_keys.example.json .\config\api_keys.json
```

Then edit:

```text
config/api_keys.json
```

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

## Settings Panel

After the app starts, open **FRIDAY SETTINGS**.

From this panel you can change:

- Voice profile
- Voice language
- Gemini API key
- Gemini Live model
- Security Center base URL
- Security Center API key

After changing Gemini model or voice settings, restart the application.

---

## Security Center Integration

Security Center integration is optional.

Use a base URL like:

```text
https://siteadi.com/security-center
```

F.R.I.D.A.Y automatically uses this endpoint:

```text
/admin/api/remote-access.php
```

So the full endpoint becomes:

```text
https://siteadi.com/security-center/admin/api/remote-access.php
```

To configure it:

1. Open F.R.I.D.A.Y.
2. Open **FRIDAY SETTINGS**.
3. Go to the **Security Center** tab.
4. Enter your Security Center base URL.
5. Enter your Security Center API key.
6. Save settings.
7. Restart F.R.I.D.A.Y if needed.

Available Security Center actions may include:

- Overview
- Latest threats
- IP profile
- IP analysis
- Health check
- Live sessions
- IP block
- Event resolve

---

## Voice Profiles

Female voice examples:

```text
Aoede
Leda
Kore
Zephyr
Callirrhoe
Autonoe
```

Male voice examples:

```text
Puck
Charon
Fenrir
Orus
Iapetus
Umbriel
Algieba
```

---

## Git Safety

Do not commit real local config or secret files:

```text
config/api_keys.json
config/friday_settings.json
config/security_center.json
config/friday_wake.json
memory/*.json
```

Only commit example config files:

```text
config/api_keys.example.json
config/friday_settings.example.json
config/security_center.example.json
config/friday_wake.example.json
```

Do not commit virtual environments:

```text
.venv/
venv/
env/
```

---

## Project Structure

```text
actions/       Command and file processing actions
agent/         Assistant/agent logic
config/        Example and local configuration files
core/          Prompt and core assistant files
memory/        Memory manager modules and local runtime memory
tools/         Utility modules and integrations
main.py        Application entry point
ui.py          Desktop interface
setup.py       Setup helper
requirements.txt
README.md
```

---

## Credits

F.R.I.D.A.Y Command Center was designed by **MEDPOV**.

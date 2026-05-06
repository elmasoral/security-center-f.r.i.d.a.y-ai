import asyncio
import re
import threading
import json
import sys
import traceback
import time
import difflib
import base64
import tempfile
import wave
from urllib.parse import quote_plus
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
try:
    from google.genai import errors as genai_errors
except Exception:
    genai_errors = None
from ui import FridayUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process, warmup_session, cancel_vision_requests
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.pc_workspace      import pc_workspace
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from tools.medpov_security_center_commands import security_center_action
import os

# --- MEDPOV FRIDAY runtime settings bridge ---
try:
    from tools.friday_settings_store import (
        bootstrap_environment,
        get_friday_voice_name,
        get_speech_config,
        get_gemini_model,
        get_friday_response_language,
        get_friday_response_language_instruction,
        get_friday_ai_provider,
        get_friday_ai_provider_label,
        get_openai_api_key,
        get_openai_realtime_model,
        get_openai_voice,
        get_friday_camera_enabled,
        get_friday_camera_disabled_message,
    )
    FRIDAY_SETTINGS = bootstrap_environment()
    FRIDAY_VOICE_NAME = get_friday_voice_name()
    FRIDAY_SPEECH_CONFIG = get_speech_config()
    FRIDAY_GEMINI_MODEL = get_gemini_model()
    FRIDAY_RESPONSE_LANGUAGE = get_friday_response_language()
    FRIDAY_RESPONSE_LANGUAGE_INSTRUCTION = get_friday_response_language_instruction()
    FRIDAY_AI_PROVIDER = get_friday_ai_provider()
    FRIDAY_AI_PROVIDER_LABEL = get_friday_ai_provider_label()
    FRIDAY_OPENAI_REALTIME_MODEL = get_openai_realtime_model()
    FRIDAY_OPENAI_VOICE = get_openai_voice()
    FRIDAY_CAMERA_ENABLED = get_friday_camera_enabled()
    FRIDAY_CAMERA_DISABLED_MESSAGE = get_friday_camera_disabled_message()
except Exception as _friday_settings_error:
    print(f"[FRIDAY] Settings bridge warning: {_friday_settings_error}")
    FRIDAY_VOICE_NAME = os.environ.get("FRIDAY_VOICE_NAME", "Aoede")
    FRIDAY_SPEECH_CONFIG = {
        "language_code": os.environ.get("FRIDAY_VOICE_LANGUAGE", "tr-TR"),
        "voice_config": {"prebuilt_voice_config": {"voice_name": FRIDAY_VOICE_NAME}},
    }
    FRIDAY_GEMINI_MODEL = os.environ.get("FRIDAY_GEMINI_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash-native-audio-preview-12-2025"
    FRIDAY_RESPONSE_LANGUAGE = os.environ.get("FRIDAY_RESPONSE_LANGUAGE", "tr")
    FRIDAY_RESPONSE_LANGUAGE_INSTRUCTION = "Her zaman Türkçe cevap ver." if FRIDAY_RESPONSE_LANGUAGE == "tr" else "Always answer in English."
    FRIDAY_AI_PROVIDER = os.environ.get("FRIDAY_AI_PROVIDER", "gemini")
    FRIDAY_AI_PROVIDER_LABEL = {"gemini":"Gemini","openai":"OpenAI","auto":"Auto / Fallback"}.get(FRIDAY_AI_PROVIDER, "Gemini")
    FRIDAY_OPENAI_REALTIME_MODEL = os.environ.get("FRIDAY_OPENAI_REALTIME_MODEL", "gpt-realtime")
    FRIDAY_OPENAI_VOICE = os.environ.get("FRIDAY_OPENAI_VOICE", "marin")
    FRIDAY_CAMERA_ENABLED = os.environ.get("FRIDAY_CAMERA_ENABLED", "1") != "0"
    FRIDAY_CAMERA_DISABLED_MESSAGE = "Camera access is currently disabled in FRIDAY settings. I cannot open the camera until Camera Access is enabled."
# --- /MEDPOV FRIDAY runtime settings bridge ---





def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
MEDPOV_PROFILE_PATH = BASE_DIR / "knowledge" / "medpov_profile.txt"
LIVE_MODEL          = "gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _live_model_name() -> str:
    """Return a Gemini Live API model supported by bidiGenerateContent.

    Important:
    - The removed/unsupported Gemini 2.0 Live ID is automatically migrated.
    - google-genai Live API works cleanly with the bare model code here.
    """
    model = str(globals().get("FRIDAY_GEMINI_MODEL", "") or LIVE_MODEL or "").strip()
    if not model:
        model = "gemini-2.5-flash-native-audio-preview-12-2025"
    if model.startswith("models/"):
        model = model.split("/", 1)[1]
    if model in ['gemini-2.0-flash-exp', 'gemini-2.0-flash-live-001', 'models/gemini-2.0-flash-exp', 'models/gemini-2.0-flash-live-001']:
        model = "gemini-2.5-flash-native-audio-preview-12-2025"
    return model

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are FRIDAY, MEDPOV's private desktop AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


def _load_medpov_profile() -> str:
    try:
        text = MEDPOV_PROFILE_PATH.read_text(encoding="utf-8").strip()
        return text[:5000]
    except Exception:
        return ""

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, webcam, what am I holding, "
            "what is in my hand, Turkish requests like 'elimde ne tutuyorum', "
            "'buna bak', 'kameraya bak', or any visual question about the real world. "
            "Use angle='camera' for webcam/hand/object/room/user questions. "
            "Use angle='screen' only for desktop/screen questions. "
            "DO NOT call this tool for audio/hearing/microphone checks such as "
            "'sesim geliyor mu', 'beni duyuyor musun', 'can you hear me', "
            "'is my voice clear', or assistant voice quality questions. Those are audio-only checks. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders in safe/trusted locations: list, create, delete, move, copy, zip, backup, rename, read, write, find, disk usage. Uses PC Settings trusted paths when available.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | zip | backup | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home, backups, screenshots, notes, or configured trusted folder"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy/zip"},
                "archive_name": {"type": "STRING", "description": "Optional zip archive name"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for or operate on"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "pc_workspace",
        "description": (
            "MEDPOV FRIDAY PC Workspace. Use for trusted PC folders, folder nicknames/aliases, project backups, zip archives, copying/moving/renaming files, screenshots, screen recording, quick notes, opening trusted folders/files, opening Word/Notepad, clipboard, disk and PC reports. "
            "Prefer this tool when the user says PC Settings, güvenilir klasör, takma ad, nickname, projelerim, proje klasörü, yedekle, zip yap, kopyala, taşı, ekran görüntüsü al, ekran kaydı al, not al, Word aç, Notepad aç, sistem raporu. "
            "File operations are allowed only inside folders added in the PC Settings panel."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "status | list_paths | aliases | add_path | remove_path | list | tree | copy | move | rename | delete | create_folder | write_text | append_text | read_text | find | recent_files | largest_files | project_summary | zip | backup | note | screenshot | screen_record | open_path | open_word | open_notepad | clipboard | disk_usage | system_report | active_window"},
                "path": {"type": "STRING", "description": "Path, trusted folder nickname/alias, or shortcut: desktop, downloads, documents, backups, screenshots, recordings, notes, projelerim, friday, etc."},
                "nickname": {"type": "STRING", "description": "Short friendly name for a trusted folder, e.g. projelerim"},
                "aliases": {"type": "STRING", "description": "Comma-separated extra aliases for a trusted folder"},
                "name": {"type": "STRING", "description": "Optional file/folder name inside path, or nickname when adding/removing folders"},
                "new_name": {"type": "STRING", "description": "New filename for rename"},
                "destination": {"type": "STRING", "description": "Destination folder nickname/path for copy/move/zip"},
                "archive_name": {"type": "STRING", "description": "Optional zip archive name"},
                "title": {"type": "STRING", "description": "Note/document title"},
                "text": {"type": "STRING", "description": "Text to write/paste/copy"},
                "content": {"type": "STRING", "description": "Note or document content"},
                "extension": {"type": "STRING", "description": "Extension for file search, e.g. .php or .pdf"},
                "mode": {"type": "STRING", "description": "Clipboard mode: read or write"},
                "clipboard_action": {"type": "STRING", "description": "Clipboard mode: read or write"},
                "depth": {"type": "INTEGER", "description": "Folder tree depth"},
                "max_items": {"type": "INTEGER", "description": "Max listed items"},
                "max_results": {"type": "INTEGER", "description": "Max search results"},
                "max_chars": {"type": "INTEGER", "description": "Max characters when reading text"},
                "count": {"type": "INTEGER", "description": "Count for recent/largest file lists"},
                "duration_seconds": {"type": "INTEGER", "description": "Screen recording duration in seconds"},
                "seconds": {"type": "INTEGER", "description": "Screen recording duration in seconds"},
                "fps": {"type": "INTEGER", "description": "Screen recording FPS"},
                "append": {"type": "BOOLEAN", "description": "Append instead of overwrite"},
                "open_after": {"type": "BOOLEAN", "description": "Open note after creating it"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_friday",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop FRIDAY. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},

    {
        "name": "security_center",
        "description": (
            "Connects to the live MEDPOV Security Center and reads or manages threats, events, IP profiles, traffic, live sessions, bots, login pressure, health reports, Security Center map intelligence, and IP rules. "
            "Use this whenever the user asks about Security Center, threats, attacks, malicious IPs, bot/scanner events, blocked requests, incident analysis, or wants to block/allow/ignore an IP. "
            "If the user asks to research an IP on the internet, first call this tool for Security Center context, then use web_search with the returned research queries if needed."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "overview | threats | events | event | ip_profile | analyze | traffic | live | bots | login | health | settings | capabilities | map_open | map_threat | map_live | map_both | map_zoom | map_close | block_ip | allow_ip | ignore_ip | resolve_event | resolve_ip_events | ai_recheck"},
                "ip": {"type": "STRING", "description": "IP address for ip_profile/analyze/block/allow/ignore/traffic"},
                "event_id": {"type": "INTEGER", "description": "Security event ID for event/analyze/resolve_event"},
                "risk": {"type": "STRING", "description": "Optional risk filter: LOW | MEDIUM | HIGH | CRITICAL"},
                "limit": {"type": "INTEGER", "description": "Number of records to return"},
                "hours": {"type": "INTEGER", "description": "Lookback period in hours"},
                "minutes": {"type": "INTEGER", "description": "Duration for temporary IP block"},
                "reason": {"type": "STRING", "description": "Reason for write actions"},
                "text": {"type": "STRING", "description": "Original user request for parsing context"},
                "mode": {"type": "STRING", "description": "Map mode for map actions: world | threat | live | both"},
                "focus": {"type": "STRING", "description": "City/place for map_zoom"},
                "threat_range": {"type": "STRING", "description": "Threat map range: 1h | 6h | 24h | 1w | 1m"},
                "live_range": {"type": "STRING", "description": "Live map range: live | 1h | 6h | 24h | 1w | 1m"}
            },
            "required": ["action"]
        }
    },

    {
        "name": "security_map",
        "description": (
            "Opens and controls the large MEDPOV Security Center global map HUD inside FRIDAY. "
            "Use this when the user says harita aç, map open, Londra aç, zoom to a city, show latest threats on map, show live connections, or show threat and live together. "
            "The map can start as a clean world map without API data, zoom to known cities, or draw Security Center map-intelligence layers from the remote API."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "map_open | map_close | map_zoom | map_threat | map_live | map_both | map_data"},
                "mode": {"type": "STRING", "description": "world | threat | live | both"},
                "focus": {"type": "STRING", "description": "City/place to focus or zoom, for example London, Londra, Istanbul, Tokyo"},
                "threat_range": {"type": "STRING", "description": "Threat map range: 1h | 6h | 24h | 1w | 1m"},
                "live_range": {"type": "STRING", "description": "Live map range: live | 1h | 6h | 24h | 1w | 1m"},
                "include_curve_points": {"type": "BOOLEAN", "description": "Whether to request curved trace points from the API"},
                "text": {"type": "STRING", "description": "Original user request for parsing context"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "friday_camera_mode",
        "description": (
            "Opens or closes the FRIDAY camera vision HUD. "
            "Use this for direct camera mode commands such as camera on/off, "
            "kamera aç/kapat, kamerayı aç/kapat, görsel moda geç. "
            "This only changes the live camera HUD; for visual analysis call screen_process with angle='camera'. "
            "Never say you cannot open or close the camera if this tool is available."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open | close"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

class _OpenAIToolCallShim:
    def __init__(self, call_id: str, name: str, args: dict):
        self.id = call_id or "openai_tool_call"
        self.name = name
        self.args = args or {}


class FridayLive:

    def __init__(self, ui: FridayUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._last_clap_time = 0.0
        self._clap_hits: list[float] = []
        self._wake_audio_queue: asyncio.Queue | None = None
        self._wake_word_notice_sent = False

        # Local camera / vision guards. These prevent Gemini Live from saying
        # "I cannot open the camera" after FRIDAY already handled the command.
        self._suppress_model_audio_until = 0.0
        self._voice_local_handled = False
        self._last_direct_camera_vision_ts = 0.0
        self._last_direct_camera_vision_text = ""
        self._last_camera_mode_command_ts = 0.0
        self._openai_voice_pending = False
        self._last_provider_command_ts = 0.0

        # OpenAI/local TTS echo protection. When FRIDAY speaks through the
        # computer speakers, Gemini's microphone transcription bridge can hear
        # that audio and send it back as if the user said it. These fields gate
        # microphone capture and filter any late assistant-echo transcripts.
        self._assistant_audio_guard_until = 0.0
        self._last_assistant_spoken_norm = ""
        self._last_assistant_spoken_raw = ""
        self._last_voice_final_norm = ""
        self._last_voice_final_ts = 0.0
        self._last_openai_command_norm = ""
        self._last_openai_command_ts = 0.0
        self._last_openai_tool_sig = ""
        self._last_openai_tool_ts = 0.0

        # OpenAI Realtime provider runtime. In OpenAI mode FRIDAY no longer
        # starts a Gemini Live session for microphone/transcription. Audio in,
        # reasoning, tool calling, and audio out all live on this websocket.
        self._openai_realtime_mode = False
        self._openai_ws = None
        self._openai_send_queue = None
        self._openai_audio_queue = None
        self._openai_loop = None
        self._openai_turn_done_event = None
        self._openai_function_args = {}
        self._openai_function_names = {}
        self._openai_assistant_buf = []
        self._openai_last_user_norm = ""
        self._openai_last_user_ts = 0.0
        self._openai_session_update_ok = False
        self._openai_session_update_retry = 0
        # Realtime API schema mode. GA must not send the old OpenAI-Beta header;
        # beta compatibility can still be selected internally if an older endpoint
        # rejects GA fields.
        self._openai_realtime_schema = "ga"
        self._openai_response_active = False
        self._openai_active_response_id = ""
        self._openai_pending_response_after_tool = False
        self._openai_executed_tool_calls = set()
        self._openai_audio_bytes_seen = 0
        self._openai_audio_chunks_seen = 0
        self._openai_audio_bytes_played = 0
        self._openai_last_assistant_text = ""
        self._openai_user_turn_id = 0
        self._openai_current_turn_tools = set()
        self._openai_camera_turn_id = -1
        self._openai_last_camera_result = ""
        self._openai_audio_drain_reports = set()
        self._openai_local_mode_handled_until = 0.0

    def _norm_text(self, text: str) -> str:
        text = (text or "").lower().strip()
        repl = str.maketrans({"ı":"i", "ğ":"g", "ü":"u", "ş":"s", "ö":"o", "ç":"c"})
        text = text.translate(repl)
        text = re.sub(r"\s+", " ", text)
        return text

    def _is_model_audio_suppressed(self) -> bool:
        return time.time() < float(getattr(self, "_suppress_model_audio_until", 0.0) or 0.0)

    def _is_assistant_audio_guard_active(self) -> bool:
        return time.time() < float(getattr(self, "_assistant_audio_guard_until", 0.0) or 0.0)

    def _begin_local_assistant_audio(self, text: str) -> None:
        norm = self._norm_text(text)
        self._last_assistant_spoken_norm = norm
        self._last_assistant_spoken_raw = str(text or "")
        # Keep the gate open while cloud TTS is generated and played. It is
        # refreshed on end with a short tail to catch speaker reverb/late STT.
        self._assistant_audio_guard_until = time.time() + 90.0
        self.set_speaking(True)

    def _end_local_assistant_audio(self) -> None:
        # Speaker audio often leaks into the microphone a few seconds after
        # playback stops, especially with laptop speakers. Keep a longer tail
        # in OpenAI provider mode because Gemini is only being used as an STT
        # bridge and should not hear FRIDAY's own OpenAI TTS output.
        self._assistant_audio_guard_until = time.time() + (5.0 if self._use_openai_brain() else 2.5)
        self.set_speaking(False)

    def _looks_like_assistant_echo(self, text: str) -> bool:
        """Return True for transcripts that are probably FRIDAY's own voice.

        This is intentionally only active during/shortly after local TTS, so a
        real user can still say similar words later without being blocked.
        """
        if not self._is_assistant_audio_guard_active():
            return False
        t = self._norm_text(text)
        last = str(getattr(self, "_last_assistant_spoken_norm", "") or "")
        if not t or not last:
            return False
        if len(t) >= 8 and (t in last or last in t):
            return True
        if len(t) >= 10 and len(last) >= 10:
            ratio = difflib.SequenceMatcher(None, t, last).ratio()
            if ratio >= 0.58:
                return True

        # Common helper phrases often leak back from speakers exactly after
        # greeting/help responses.
        echo_phrases = (
            "sana nasil yardimci olabilirim",
            "size nasil yardimci olabilirim",
            "hangi konuda destek",
            "ne yapmak istersiniz",
            "sorularinizi veya isteklerinizi",
            "yardimci olmaya hazirim",
            "how can i help",
            "how may i help",
        )
        if any(p in t for p in echo_phrases):
            return True

        tw = [w for w in t.split() if len(w) > 2]
        lw = [w for w in last.split() if len(w) > 2]
        if len(tw) >= 3 and lw:
            overlap = len(set(tw) & set(lw)) / max(1, len(set(tw)))
            if overlap >= 0.62:
                return True
        return False


    def _command_provider(self) -> str:
        return str(globals().get("FRIDAY_AI_PROVIDER", "gemini") or "gemini").strip().lower()

    def _use_openai_brain(self) -> bool:
        return self._command_provider() == "openai"

    def _use_openai_realtime(self) -> bool:
        return self._command_provider() == "openai"

    def _openai_realtime_model(self) -> str:
        return str(globals().get("FRIDAY_OPENAI_REALTIME_MODEL", "") or "gpt-realtime").strip()

    def _openai_realtime_voice(self) -> str:
        return str(globals().get("FRIDAY_OPENAI_VOICE", "") or "marin").strip()

    def _to_openai_realtime_tools(self) -> list[dict]:
        def lower_schema(value):
            if isinstance(value, dict):
                out = {}
                for k, v in value.items():
                    if k == "type" and isinstance(v, str):
                        out[k] = v.lower()
                    elif k == "properties" and isinstance(v, dict):
                        out[k] = {name: lower_schema(schema) for name, schema in v.items()}
                    elif k == "items":
                        out[k] = lower_schema(v)
                    else:
                        out[k] = lower_schema(v)
                return out
            if isinstance(value, list):
                return [lower_schema(x) for x in value]
            return value

        tools = []
        for decl in TOOL_DECLARATIONS:
            name = str(decl.get("name") or "").strip()
            if not name:
                continue
            params = lower_schema(decl.get("parameters") or {"type": "object", "properties": {}})
            params.setdefault("type", "object")
            tools.append({
                "type": "function",
                "name": name,
                "description": str(decl.get("description") or ""),
                "parameters": params,
            })
        return tools

    def _openai_realtime_instructions(self) -> str:
        from datetime import datetime
        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        now = datetime.now().strftime("%A, %B %d, %Y — %I:%M %p")
        base = _load_system_prompt()
        medpov_profile = _load_medpov_profile()
        camera_guard = (
            "Camera access is enabled. Use camera tools only when requested or required."
            if self._camera_is_enabled()
            else "Camera access is disabled by user settings. If the user asks to open/use/analyze camera, refuse briefly and say Camera Access is disabled. Do not call camera tools."
        )
        parts = [
            "You are F.R.I.D.A.Y, MEDPOV's private desktop AI command center.",
            "You are running on the OpenAI Realtime provider only. Do not mention Gemini. Do not claim a tool result unless a tool has been executed.",
            "Speak naturally, smoothly, and briefly like a premium desktop assistant. Avoid long lists unless the user asks.",
            "Use tools for desktop actions, camera/screen analysis, files, web, reminders, and Security Center.",
            "For map commands such as harita aç, Londra aç, latest threats on map, live connections, or both layers, call security_map instead of answering verbally. The map HUD is a local visual mode, similar to camera mode.",
            "FRIDAY runtime commands are NOT computer settings. If the user says standby, stand by, bekleme moduna geç, bekleme modunu aktif et, dinlemeyi durdur, or sleep mode, do not call computer_settings; switch to standby/listening state only.",
            "You do NOT have live visual access by default. If the user asks anything like 'do you see me', 'what am I holding', 'look at the camera', 'kameraya bak', 'beni görüyor musun', or any real-world visual question, you MUST call screen_process with angle='camera' before answering.",
            "Audio/hearing checks are NOT visual requests. For phrases like 'sesim geliyor mu', 'beni duyuyor musun', 'sesin geliyor mu', 'can you hear me', or 'is my voice clear', answer from the live audio connection only. Do NOT open the camera and do NOT call screen_process.",
            "If the user asks to evaluate FRIDAY's voice, microphone, speaker, or sound quality, do not use the camera; answer briefly or ask for an audio-specific detail.",
            "Never invent camera observations. Only describe the camera/screen after screen_process returns a result.",
            camera_guard,
            "When a tool returns a direct result, summarize it in a short human sentence.",
            f"Current date/time: {now}.",
            FRIDAY_RESPONSE_LANGUAGE_INSTRUCTION,
            base,
        ]
        if medpov_profile:
            parts.append("MEDPOV permanent profile:\n" + medpov_profile)
        if mem_str:
            parts.append(mem_str)
        return "\n\n".join(p for p in parts if p)

    def _openai_realtime_session_update(self, legacy: bool = False) -> dict:
        """Build a Realtime session.update payload.

        v2.8.3 keeps the GA Realtime schema strict and explicit. The previous patch kept the
        beta websocket header while sending GA fields; that is why the server
        rejected earlier audio fields. GA mode must send the PCM format with
        both `type` and `rate` for input and output audio. If an older beta
        endpoint is detected, legacy=True uses the older flat schema with
        `modalities` instead.
        """
        lang = "tr" if FRIDAY_RESPONSE_LANGUAGE == "tr" else "en"
        voice = self._openai_realtime_voice()

        if legacy:
            return {
                "type": "session.update",
                "session": {
                    "instructions": self._openai_realtime_instructions(),
                    "modalities": ["audio", "text"],
                    "voice": voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "gpt-4o-mini-transcribe",
                        "language": lang,
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.52,
                        "prefix_padding_ms": 260,
                        "silence_duration_ms": 620,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                    "tools": self._to_openai_realtime_tools(),
                    "tool_choice": "auto",
                },
            }

        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self._openai_realtime_model(),
                "instructions": self._openai_realtime_instructions(),
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "transcription": {
                            "model": "gpt-4o-mini-transcribe",
                            "language": lang,
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.52,
                            "prefix_padding_ms": 260,
                            "silence_duration_ms": 620,
                            "create_response": True,
                            "interrupt_response": True,
                        },
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": voice,
                    },
                },
                "tools": self._to_openai_realtime_tools(),
                "tool_choice": "auto",
                "max_output_tokens": 900,
            },
        }

    def _queue_openai_event_threadsafe(self, event: dict) -> bool:
        q = getattr(self, "_openai_send_queue", None)
        loop = getattr(self, "_openai_loop", None)
        if not q or not loop:
            return False
        def _push():
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(event)
                except Exception:
                    pass
        try:
            loop.call_soon_threadsafe(_push)
            return True
        except Exception:
            return False

    def _openai_request_audio_response(self) -> dict:
        """Create one audio response request for the active Realtime schema.

        Important: only one response can be active in a Realtime conversation.
        Calls to this method are now routed through the active-response guard
        below so we do not spam response.create while the previous answer or
        tool-call turn is still in progress.
        """
        if str(getattr(self, "_openai_realtime_schema", "ga") or "ga") == "beta":
            return {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "voice": self._openai_realtime_voice(),
                    "instructions": "Cevabı doğal, kısa ve sesli şekilde ver.",
                },
            }
        return {
            "type": "response.create",
            "response": {
                "output_modalities": ["audio"],
                "instructions": "Cevabı doğal, kısa ve sesli şekilde ver. Ses üret; yalnızca metin üretme.",
                "audio": {
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": self._openai_realtime_voice(),
                    }
                },
            },
        }

    def _openai_queue_response_create(self, *, cancel_active: bool = False, after_tool: bool = False) -> bool:
        """Queue response.create safely without triggering active-response errors."""
        if bool(getattr(self, "_openai_response_active", False)):
            if cancel_active:
                self._queue_openai_event_threadsafe({"type": "response.cancel"})
                self._openai_response_active = False
                self._openai_active_response_id = ""
            else:
                self._openai_pending_response_after_tool = bool(after_tool or True)
                return True
        return self._queue_openai_event_threadsafe(self._openai_request_audio_response())

    async def _openai_send_response_create(self, ws, *, after_tool: bool = False) -> None:
        """Send response.create from the websocket loop with active-response protection."""
        if bool(getattr(self, "_openai_response_active", False)):
            self._openai_pending_response_after_tool = bool(after_tool or True)
            return
        await ws.send(json.dumps(self._openai_request_audio_response(), ensure_ascii=False))

    def _openai_retry_session_update_from_error(self, msg: str) -> bool:
        """Retry session.update once across GA/Beta schema differences."""
        if getattr(self, "_openai_session_update_ok", False):
            return False
        low = (msg or "").lower()
        if "unknown parameter" not in low and "missing required parameter" not in low:
            return False
        if int(getattr(self, "_openai_session_update_retry", 0) or 0) >= 1:
            return False

        # If GA fields are rejected, downgrade the payload to the old flat beta
        # field names inside the same socket. The next reconnect also uses the
        # beta header via _openai_realtime_schema.
        if "session.type" in low or "session.output_modalities" in low or "session.audio" in low or "session.noise_reduction" in low:
            # GA accepts audio.output.format.rate, while beta does not understand
            # the nested audio object. If the GA endpoint asks for the rate, the
            # current patched payload already includes it; do not downgrade.
            if "session.audio.output.format.rate" in low:
                self._openai_session_update_retry = 1
                return self._queue_openai_event_threadsafe(self._openai_realtime_session_update(legacy=False))
            self._openai_session_update_retry = 1
            self._openai_realtime_schema = "beta"
            self.ui.write_log("SYS: OpenAI Realtime eski şema uyumluluk modu etkinleştirildi.")
            return self._queue_openai_event_threadsafe(self._openai_realtime_session_update(legacy=True))
        return False

    def _send_openai_text_turn(self, text: str) -> bool:
        raw = (text or "").strip()
        if not raw:
            return False
        now = time.time()
        norm = self._norm_text(raw)
        if norm and norm == str(getattr(self, "_openai_last_user_norm", "") or "") and now - float(getattr(self, "_openai_last_user_ts", 0.0) or 0.0) < 1.2:
            return True
        self._openai_user_turn_id = int(getattr(self, "_openai_user_turn_id", 0) or 0) + 1
        self._openai_current_turn_tools = set()
        self._openai_last_user_norm = norm
        self._openai_last_user_ts = now
        ok1 = self._queue_openai_event_threadsafe({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": raw}],
            },
        })
        # Text/direct-command turns are user interruptions. Cancel any unfinished
        # assistant response first, then ask for exactly one new audio response.
        ok2 = self._openai_queue_response_create(cancel_active=True)
        return bool(ok1 and ok2)

    def _openai_realtime_say(self, text: str) -> None:
        msg = (text or "").strip()
        if not msg:
            return
        self._send_openai_text_turn("Sadece şu sonucu kullanıcıya doğal şekilde söyle, yeni işlem başlatma: " + msg)

    def _openai_realtime_stop_audio(self) -> None:
        q = getattr(self, "_openai_audio_queue", None)
        if q:
            try:
                while True:
                    q.get_nowait()
            except Exception:
                pass
        self.set_speaking(False)

    def _openai_tool_signature(self, name: str, args: dict) -> str:
        """Stable per-user-turn tool signature to stop Realtime tool loops."""
        safe_args = {}
        for k, v in dict(args or {}).items():
            if str(k).startswith("_"):
                continue
            safe_args[str(k)] = v
        try:
            blob = json.dumps(safe_args, ensure_ascii=False, sort_keys=True)
        except Exception:
            blob = str(safe_args)
        return f"{int(getattr(self, '_openai_user_turn_id', 0) or 0)}:{name}:{blob}"

    def _openai_should_skip_tool_loop(self, name: str, args: dict) -> str | None:
        """Return a safe tool output when the model is repeating a tool call.

        OpenAI Realtime can ask the same function through multiple lifecycle
        events or keep calling camera again inside the same assistant turn. One
        real user turn should get one camera observation; follow-up user speech
        resets the turn id and unlocks the camera again.
        """
        sig = self._openai_tool_signature(name, args)
        seen = getattr(self, "_openai_current_turn_tools", set()) or set()
        if sig in seen:
            return "Bu araç çağrısı bu kullanıcı turunda zaten çalıştırıldı. Sonuca göre kısa cevap ver; aynı aracı tekrar çağırma."
        seen.add(sig)
        self._openai_current_turn_tools = seen

        if name == "screen_process":
            angle = str((args or {}).get("angle") or "screen").lower().strip()
            tool_text = str((args or {}).get("text") or "")
            if angle == "camera":
                if not self._camera_is_enabled():
                    return self._camera_disabled_reply() + " Do not call camera tools again unless Camera Access is enabled."
                # Hard safety gate: the model sometimes confuses hearing/audio
                # checks with visual checks. Do not let those calls open the camera.
                if self._looks_like_audio_status_request(tool_text):
                    return (
                        "Bu istek kamera/görüntü analizi gerektirmiyor; bu bir ses, mikrofon veya duyma kontrolü. "
                        "Kamerayı açma. Kullanıcıya sesini duyduğunu veya ses konusundaki durumu kısa ve doğal şekilde söyle."
                    )
                turn_id = int(getattr(self, "_openai_user_turn_id", 0) or 0)
                if int(getattr(self, "_openai_camera_turn_id", -1) or -1) == turn_id:
                    last = str(getattr(self, "_openai_last_camera_result", "") or "Görüntü analizi bu turda zaten yapıldı.")
                    return "Kamera bu kullanıcı turunda zaten analiz edildi. Son kamera sonucu: " + last + " Buna göre kısa cevap ver; kullanıcı yeni bir komut vermeden tekrar kamera çağırma."
                self._openai_camera_turn_id = turn_id
        return None

    async def _openai_report_audio_drain(self, response_id: str, transcript: str, seen_at_done: int) -> None:
        """Wait for realtime audio playback to drain, then diagnose/fallback.

        response.done can arrive before the local speaker queue has finished
        playing. The old log therefore looked like audio was missing even when
        chunks were still queued. This waits briefly and only uses Speech API
        fallback when playback did not materially advance.
        """
        response_id = str(response_id or f"resp_{int(time.time()*1000)}")
        reports = getattr(self, "_openai_audio_drain_reports", set()) or set()
        if response_id in reports:
            return
        reports.add(response_id)
        self._openai_audio_drain_reports = reports

        start = time.time()
        # 24 kHz, PCM16 mono => 48,000 bytes/second. Give the queue enough time
        # to drain without blocking the websocket receive loop.
        expected_sec = max(0.6, min(12.0, float(seen_at_done or 0) / 48000.0 + 0.8))
        while time.time() - start < expected_sec:
            q = getattr(self, "_openai_audio_queue", None)
            played = int(getattr(self, "_openai_audio_bytes_played", 0) or 0)
            seen_now = int(getattr(self, "_openai_audio_bytes_seen", 0) or 0)
            if seen_now > 0 and played >= int(seen_now * 0.96) and (not q or q.empty()):
                print(f"[OpenAI RT] audio drain ok — seen={seen_now:,} bytes, played={played:,} bytes")
                return
            await asyncio.sleep(0.12)

        played = int(getattr(self, "_openai_audio_bytes_played", 0) or 0)
        seen_now = int(getattr(self, "_openai_audio_bytes_seen", 0) or 0)
        qsize = 0
        try:
            q = getattr(self, "_openai_audio_queue", None)
            qsize = q.qsize() if q else 0
        except Exception:
            qsize = 0
        print(f"[OpenAI RT] audio drain warning — seen={seen_now:,} bytes, played={played:,} bytes, queue={qsize}")

        # If the realtime player did not play enough audio, use the reliable
        # WAV fallback even though realtime chunks arrived. This prevents silent
        # answers on Windows devices that accept PortAudio writes but output no sound.
        if transcript and seen_now > 0 and played < int(seen_now * 0.45):
            await self._openai_tts_wav_fallback(transcript)

    async def _openai_execute_tool_result(self, ws, name: str, args: dict, call_id: str) -> None:
        name = str(name or "").strip()
        args = dict(args or {})
        call_id = str(call_id or "").strip() or f"call_{int(time.time()*1000)}"
        # Realtime can surface the same tool call through several lifecycle
        # events. Execute each call_id only once, otherwise Security Center and
        # camera calls repeat and then response.create collides with an active turn.
        seen = getattr(self, "_openai_executed_tool_calls", set())
        if call_id in seen:
            print(f"[OpenAI RT] ↩ duplicate tool call ignored: {name} {call_id}")
            return
        seen.add(call_id)
        self._openai_executed_tool_calls = seen
        self.ui.set_state("THINKING")
        print(f"[OpenAI RT] 🔧 {name} {args}")
        local_mode_output = self._handle_realtime_mode_tool_action(name, args, source="openai-tool")
        output = local_mode_output or self._openai_should_skip_tool_loop(name, args) or "Done."
        try:
            if output != "Done.":
                pass
            elif name == "screen_process":
                angle = str(args.get("angle") or "screen").lower().strip()
                if angle == "camera" and not self._camera_is_enabled():
                    output = self._camera_disabled_reply()
                elif angle == "camera":
                    cancel_vision_requests()
                    if hasattr(self.ui, "start_camera_mode"):
                        self.ui.start_camera_mode(camera_index=None)
                    args["_camera_started"] = True
                args["_return_text"] = True
                args["_silent"] = True
                loop = asyncio.get_event_loop()
                r = await loop.run_in_executor(None, lambda: screen_process(parameters=args, response=None, player=self.ui, session_memory=None))
                output = str(r or "Görüntü analizi tamamlandı ama net sonuç alınamadı.")
                if str(args.get("angle") or "").lower().strip() == "camera":
                    self._openai_last_camera_result = output
            else:
                shim = _OpenAIToolCallShim(call_id, name, args)
                fr = await self._execute_tool(shim)
                payload = getattr(fr, "response", None) or {}
                if isinstance(payload, dict):
                    output = str(payload.get("result") or payload or "Done.")
                else:
                    output = str(payload or "Done.")
        except Exception as exc:
            output = f"Tool '{name}' failed: {exc}"
            traceback.print_exc()

        await ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps({"result": output, "instruction": "Bu tool sonucuna göre kullanıcıya kısa ve doğal cevap ver. Aynı tool'u tekrar çağırma."}, ensure_ascii=False),
            },
        }, ensure_ascii=False))
        if local_mode_output and self.ui.standby:
            self._openai_pending_response_after_tool = False
            self._openai_realtime_stop_audio()
            self.ui.set_state("STANDBY")
            return
        await self._openai_send_response_create(ws, after_tool=True)

    def _maybe_tool_from_output_item(self, event: dict) -> tuple[str, dict, str] | None:
        item = event.get("item") or event.get("output_item") or {}
        if not isinstance(item, dict):
            return None
        if str(item.get("type") or "") not in {"function_call", "tool_call"}:
            return None
        name = str(item.get("name") or "").strip()
        call_id = str(item.get("call_id") or item.get("id") or event.get("call_id") or "").strip()
        raw_args = item.get("arguments") or item.get("args") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
        except Exception:
            args = {}
        return name, args, call_id

    async def _openai_ws_send_loop(self, ws):
        while True:
            event = await self._openai_send_queue.get()
            await ws.send(json.dumps(event, ensure_ascii=False))

    async def _openai_listen_audio(self):
        print("[OpenAI RT] 🎤 Mic started")
        loop = asyncio.get_event_loop()
        sample_rate = 24000

        def callback(indata, frames, time_info, status):
            if self.ui.muted:
                return
            data = indata.tobytes()
            if self.ui.standby:
                self._handle_standby_audio_gate(indata, data, loop)
                return
            with self._speaking_lock:
                speaking = self._is_speaking
            # Speaker->microphone echo is the biggest practical problem on a desktop.
            # Keep mic quiet while FRIDAY is talking; text commands still work.
            if speaking:
                return
            b64 = base64.b64encode(data).decode("ascii")
            def _safe_push():
                try:
                    self._openai_send_queue.put_nowait({"type": "input_audio_buffer.append", "audio": b64})
                except asyncio.QueueFull:
                    pass
            loop.call_soon_threadsafe(_safe_push)

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[OpenAI RT] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as exc:
            print(f"[OpenAI RT] ❌ Mic: {exc}")
            raise

    def _openai_write_pcm_chunk(self, stream, chunk: bytes) -> int:
        """Write raw PCM16 mono audio to sounddevice reliably.

        RawOutputStream is picky on some Windows devices. OutputStream + numpy
        lets PortAudio handle the device conversion more reliably.
        """
        try:
            import numpy as np
            arr = np.frombuffer(chunk, dtype=np.int16)
            if CHANNELS > 1:
                usable = (len(arr) // CHANNELS) * CHANNELS
                arr = arr[:usable].reshape(-1, CHANNELS)
            stream.write(arr)
            return int(len(chunk))
        except Exception:
            # Last resort: if a RawOutputStream was used, bytes are accepted.
            try:
                stream.write(chunk)
                return int(len(chunk))
            except Exception:
                raise

    async def _openai_tts_wav_fallback(self, text: str) -> None:
        """Play a guaranteed WAV fallback through the system device.

        If the Realtime socket returns only transcript text, the user gets a
        silent assistant. This fallback asks OpenAI's speech endpoint for a WAV
        using the same selected voice and plays it with Windows' system audio
        stack when available. It is not used when realtime audio deltas arrive.
        """
        msg = (text or "").strip()
        if not msg:
            return
        api_key = (get_openai_api_key() or os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            return
        try:
            import requests
            def _fetch():
                return requests.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": "Bearer " + api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini-tts",
                        "voice": self._openai_realtime_voice(),
                        "input": msg[:3500],
                        "instructions": "Türkçe doğal, akıcı, kısa ve net konuş. Masaüstü asistanı gibi sıcak bir ton kullan.",
                        "response_format": "wav",
                    },
                    timeout=45,
                )
            res = await asyncio.to_thread(_fetch)
            if getattr(res, "status_code", 0) >= 400:
                print(f"[OpenAI RT] ⚠️ TTS fallback HTTP {res.status_code}: {getattr(res, 'text', '')[:160]}")
                return
            data = bytes(res.content or b"")
            if len(data) < 128:
                return

            self.set_speaking(True)
            self._assistant_audio_guard_until = time.time() + 90.0
            print(f"[OpenAI RT] 🔊 TTS fallback WAV {len(data):,} bytes")

            if os.name == "nt":
                def _play_win():
                    import winsound
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                    try:
                        tmp.write(data); tmp.flush(); tmp.close()
                        winsound.PlaySound(tmp.name, winsound.SND_FILENAME)
                    finally:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                await asyncio.to_thread(_play_win)
            else:
                def _play_wave():
                    import numpy as np
                    import io
                    with wave.open(io.BytesIO(data), "rb") as wf:
                        rate = wf.getframerate()
                        channels = wf.getnchannels()
                        pcm = wf.readframes(wf.getnframes())
                    arr = np.frombuffer(pcm, dtype=np.int16)
                    if channels > 1:
                        arr = arr.reshape(-1, channels)
                    sd.play(arr, samplerate=rate, blocking=True)
                await asyncio.to_thread(_play_wave)
        except Exception as exc:
            print(f"[OpenAI RT] ⚠️ TTS fallback failed: {exc}")
        finally:
            self._assistant_audio_guard_until = time.time() + 4.0
            self.set_speaking(False)

    async def _openai_play_audio(self):
        print("[OpenAI RT] 🔊 Play started")
        stream = None
        try:
            stream = sd.OutputStream(
                samplerate=24000,
                channels=CHANNELS,
                dtype="int16",
                blocksize=0,
            )
            stream.start()
        except Exception as exc:
            print(f"[OpenAI RT] ❌ Audio output disabled: {exc}")
            self.ui.write_log("SYS: OpenAI audio output unavailable. FRIDAY continues in text/log mode.")
            while True:
                await self._openai_audio_queue.get()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(self._openai_audio_queue.get(), timeout=0.12)
                except asyncio.TimeoutError:
                    if self._openai_turn_done_event and self._openai_turn_done_event.is_set() and self._openai_audio_queue.empty():
                        self.set_speaking(False)
                        self._openai_turn_done_event.clear()
                    continue
                if self.ui.standby:
                    self.set_speaking(False)
                    continue
                self.set_speaking(True)
                played = await asyncio.to_thread(self._openai_write_pcm_chunk, stream, chunk)
                self._openai_audio_bytes_played = int(getattr(self, "_openai_audio_bytes_played", 0) or 0) + int(played or 0)
        except Exception as exc:
            print(f"[OpenAI RT] ❌ Play: {exc}")
            raise
        finally:
            self.set_speaking(False)
            try:
                if stream:
                    stream.stop(); stream.close()
            except Exception:
                pass

    async def _openai_recv_loop(self, ws):
        print("[OpenAI RT] 👂 Recv started")
        assistant_parts: list[str] = []
        text_parts: list[str] = []
        while True:
            raw = await ws.recv()
            try:
                event = json.loads(raw)
            except Exception:
                continue
            etype = str(event.get("type") or "")

            if etype == "error":
                err = event.get("error") or {}
                msg = str(err.get("message") or event)
                print(f"[OpenAI RT] ❌ {msg}")
                low_msg = msg.lower()
                if self._openai_retry_session_update_from_error(msg):
                    continue
                if "active response in progress" in low_msg:
                    # Benign race: the server is still finishing the previous
                    # response. Do not spam the UI; ask again after response.done.
                    self._openai_pending_response_after_tool = True
                    continue
                self.ui.write_log("ERR: OpenAI Realtime — " + msg[:180])
                continue

            if etype == "session.created":
                self._openai_response_active = False
                self._openai_active_response_id = ""
                print(f"[OpenAI RT] ✅ {etype}")
                continue

            if etype == "session.updated":
                self._openai_session_update_ok = True
                self._openai_session_update_retry = 0
                print(f"[OpenAI RT] ✅ {etype}")
                self.ui.write_log("SYS: OpenAI Realtime audio session ready.")
                continue

            if etype == "response.created":
                resp = event.get("response") or {}
                self._openai_response_active = True
                self._openai_active_response_id = str(resp.get("id") or event.get("response_id") or "")
                self._openai_audio_bytes_seen = 0
                self._openai_audio_chunks_seen = 0
                self._openai_audio_bytes_played = 0
                assistant_parts = []
                text_parts = []
                if time.time() < float(getattr(self, "_openai_local_mode_handled_until", 0.0) or 0.0):
                    try:
                        await ws.send(json.dumps({"type": "response.cancel"}, ensure_ascii=False))
                    except Exception:
                        pass
                    self._openai_response_active = False
                    self._openai_active_response_id = ""
                    self._openai_realtime_stop_audio()
                    if self.ui.standby:
                        self.ui.set_state("STANDBY")
                    continue
                continue

            if etype in {"response.cancelled", "response.canceled"}:
                self._openai_response_active = False
                self._openai_active_response_id = ""
                self._openai_realtime_stop_audio()
                continue

            if etype == "input_audio_buffer.speech_started":
                if self.ui.standby:
                    self.ui.set_state("STANDBY")
                    continue
                # Let the user barge in naturally: stop any queued assistant
                # audio as soon as the server detects new speech. If a response
                # is still active, cancel it before the next turn to prevent the
                # "active response in progress" error.
                if bool(getattr(self, "_openai_response_active", False)):
                    self._queue_openai_event_threadsafe({"type": "response.cancel"})
                    self._openai_response_active = False
                    self._openai_active_response_id = ""
                self._openai_realtime_stop_audio()
                self.ui.set_state("LISTENING")
                continue

            if etype in {"input_audio_buffer.speech_stopped", "input_audio_buffer.committed"}:
                self.ui.set_state("THINKING")
                continue

            if etype in {"conversation.item.input_audio_transcription.completed", "conversation.item.input_audio_transcription.done", "conversation.item.input_audio_transcription.finished"}:
                txt = _clean_transcript(str(event.get("transcript") or event.get("text") or ""))
                if not txt and isinstance(event.get("item"), dict):
                    txt = _clean_transcript(str((event.get("item") or {}).get("transcript") or ""))
                if txt:
                    norm = self._norm_text(txt)
                    now = time.time()
                    if not (norm == self._last_voice_final_norm and now - self._last_voice_final_ts < 2.5):
                        self._last_voice_final_norm = norm
                        self._last_voice_final_ts = now
                        self._openai_user_turn_id = int(getattr(self, "_openai_user_turn_id", 0) or 0) + 1
                        self._openai_current_turn_tools = set()
                        self.ui.write_log(f"You: {txt}")

                        # Hard local mode commands must win over Realtime model/tool routing.
                        # Without this, "bekleme moduna geç" can be routed as
                        # computer_settings(action=standby), which is not an OS action.
                        if self._handle_friday_mode_command(txt, source="openai-voice"):
                            self._openai_local_mode_handled_until = time.time() + 2.5
                            self._openai_pending_response_after_tool = False
                            self._openai_realtime_stop_audio()
                            if bool(getattr(self, "_openai_response_active", False)):
                                try:
                                    await ws.send(json.dumps({"type": "response.cancel"}, ensure_ascii=False))
                                except Exception:
                                    pass
                                self._openai_response_active = False
                                self._openai_active_response_id = ""
                            if self.ui.standby:
                                self.ui.set_state("STANDBY")
                continue

            if etype in {"response.audio.delta", "response.output_audio.delta"}:
                delta = event.get("delta") or event.get("audio") or ""
                if delta:
                    try:
                        decoded = base64.b64decode(delta)
                        self._openai_audio_chunks_seen = int(getattr(self, "_openai_audio_chunks_seen", 0) or 0) + 1
                        self._openai_audio_bytes_seen = int(getattr(self, "_openai_audio_bytes_seen", 0) or 0) + len(decoded)
                        if int(getattr(self, "_openai_audio_chunks_seen", 0) or 0) == 1:
                            print(f"[OpenAI RT] 🔊 first realtime audio chunk: {len(decoded):,} bytes")
                        try:
                            self._openai_audio_queue.put_nowait(decoded)
                        except asyncio.QueueFull:
                            # Drop the oldest unplayed chunk rather than the newest; this
                            # keeps the assistant closer to real time while avoiding silence.
                            try:
                                self._openai_audio_queue.get_nowait()
                            except Exception:
                                pass
                            self._openai_audio_queue.put_nowait(decoded)
                    except Exception as exc:
                        print(f"[OpenAI RT] ⚠️ audio delta ignored: {exc}")
                continue

            if etype in {"response.audio_transcript.delta", "response.output_audio_transcript.delta"}:
                delta = str(event.get("delta") or "")
                if delta:
                    assistant_parts.append(delta)
                continue

            if etype in {"response.text.delta", "response.output_text.delta"}:
                delta = str(event.get("delta") or "")
                if delta:
                    text_parts.append(delta)
                continue

            if etype.endswith("function_call_arguments.delta"):
                call_id = str(event.get("call_id") or event.get("item_id") or event.get("output_index") or "")
                if call_id:
                    self._openai_function_args[call_id] = self._openai_function_args.get(call_id, "") + str(event.get("delta") or "")
                    if event.get("name"):
                        self._openai_function_names[call_id] = str(event.get("name") or "")
                continue

            if etype.endswith("function_call_arguments.done"):
                call_id = str(event.get("call_id") or event.get("item_id") or event.get("output_index") or "")
                name = str(event.get("name") or self._openai_function_names.get(call_id, "") or "")
                raw_args = str(event.get("arguments") or self._openai_function_args.get(call_id, "{}") or "{}")
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
                if name:
                    asyncio.create_task(self._openai_execute_tool_result(ws, name, args, call_id))
                continue

            if etype == "response.output_item.done":
                maybe = self._maybe_tool_from_output_item(event)
                if maybe:
                    name, args, call_id = maybe
                    asyncio.create_task(self._openai_execute_tool_result(ws, name, args, call_id))
                continue

            if etype in {"response.output_audio_transcript.done", "response.audio_transcript.done"}:
                final_tx = str(event.get("transcript") or event.get("text") or "").strip()
                if final_tx and not assistant_parts:
                    assistant_parts.append(final_tx)
                continue

            if etype in {"response.audio.done", "response.output_audio.done"}:
                if self._openai_turn_done_event:
                    self._openai_turn_done_event.set()
                continue

            if etype == "response.done":
                self._openai_response_active = False
                self._openai_active_response_id = ""
                found_tool = False
                # Some SDK/API variants only expose tool calls inside response.done.
                try:
                    resp = event.get("response") or {}
                    for item in resp.get("output", []) or []:
                        if isinstance(item, dict) and item.get("type") == "function_call":
                            name = str(item.get("name") or "")
                            call_id = str(item.get("call_id") or item.get("id") or "")
                            raw_args = item.get("arguments") or "{}"
                            try:
                                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
                            except Exception:
                                args = {}
                            if name:
                                found_tool = True
                                asyncio.create_task(self._openai_execute_tool_result(ws, name, args, call_id))
                except Exception:
                    pass
                full = re.sub(r"\s+", " ", "".join(assistant_parts or text_parts)).strip()
                if full:
                    self._openai_last_assistant_text = full
                    self.ui.write_log("FRIDAY: " + full)
                    # If the socket returned only transcript/text and no audio
                    # bytes, force a reliable OpenAI TTS WAV fallback so FRIDAY
                    # is never silent.
                    if int(getattr(self, "_openai_audio_bytes_seen", 0) or 0) <= 0:
                        asyncio.create_task(self._openai_tts_wav_fallback(full))
                audio_seen = int(getattr(self, "_openai_audio_bytes_seen", 0) or 0)
                played = int(getattr(self, "_openai_audio_bytes_played", 0) or 0)
                qsize = 0
                try:
                    qsize = self._openai_audio_queue.qsize() if self._openai_audio_queue else 0
                except Exception:
                    qsize = 0
                response_id = str((event.get("response") or {}).get("id") or self._openai_active_response_id or "")
                if full:
                    print(f"[OpenAI RT] turn done — audio_seen={audio_seen:,} bytes, played_now={played:,} bytes, queue={qsize}")
                    asyncio.create_task(self._openai_report_audio_drain(response_id, full, audio_seen))
                assistant_parts = []
                text_parts = []
                if self._openai_turn_done_event:
                    self._openai_turn_done_event.set()
                if self._openai_pending_response_after_tool and not found_tool:
                    self._openai_pending_response_after_tool = False
                    await self._openai_send_response_create(ws, after_tool=True)
                    continue
                if self.ui.standby:
                    self.ui.set_state("STANDBY")
                elif not self.ui.muted:
                    self.ui.set_state("LISTENING")
                continue

    def _local_tts(self, text: str) -> None:
        if bool(getattr(self, "_openai_realtime_mode", False)):
            self._openai_realtime_say(text)
            return
        try:
            from tools.friday_local_tts import speak_text_async
            if bool(getattr(self.ui, "muted", False)):
                return
            speak_text_async(
                text,
                muted=False,
                on_start=lambda: self._begin_local_assistant_audio(text),
                on_end=self._end_local_assistant_audio,
            )
        except Exception as exc:
            print(f"[FRIDAY] Local TTS skipped: {exc}")

    def _handle_openai_text_command(self, text: str, source: str = "text") -> bool:
        raw = (text or "").strip()
        if not raw:
            return False

        now = time.time()
        norm_raw = self._norm_text(raw)

        # In OpenAI mode Gemini is only an STT bridge. Do not route anything
        # heard while FRIDAY's OpenAI TTS is still playing or tailing off.
        if source.startswith("voice") and self._is_assistant_audio_guard_active():
            return True
        if source.startswith("voice") and self._looks_like_assistant_echo(raw):
            return True

        # Avoid duplicate partial/final voice transcripts and delayed echo
        # fragments hitting OpenAI twice.
        if source.startswith("voice") and now - float(getattr(self, "_last_provider_command_ts", 0.0) or 0.0) < 1.35:
            return True
        last_norm = str(getattr(self, "_last_openai_command_norm", "") or "")
        last_ts = float(getattr(self, "_last_openai_command_ts", 0.0) or 0.0)
        if source.startswith("voice") and norm_raw and last_norm and now - last_ts < 5.0:
            if norm_raw == last_norm or norm_raw in last_norm or last_norm in norm_raw:
                return True
            if difflib.SequenceMatcher(None, norm_raw, last_norm).ratio() >= 0.74:
                return True
        self._last_provider_command_ts = now
        self._last_openai_command_norm = norm_raw
        self._last_openai_command_ts = now

        def _worker():
            try:
                self.ui.set_state("THINKING")
                self.ui.write_log("SYS: OpenAI provider command routing...")
                from providers.openai_provider import route_command
                result = route_command(raw, TOOL_DECLARATIONS, system_prompt=(
                    "You are F.R.I.D.A.Y, MEDPOV's private desktop AI command center. "
                    "Use the declared tools for desktop actions, files, camera, reminders, web, and Security Center. "
                    "Keep responses concise. " + FRIDAY_RESPONSE_LANGUAGE_INSTRUCTION
                ))
                if result.error:
                    msg = "OpenAI provider error: " + result.error
                    self.ui.write_log("ERR: " + msg)
                    self._local_tts(msg)
                    return

                tool_calls = result.tool_calls or []
                if tool_calls:
                    summaries = []
                    silent_tool_names = {"screen_process", "friday_camera_mode"}
                    for call in tool_calls[:3]:
                        sig = f"{call.name}:{json.dumps(call.args or {}, sort_keys=True, ensure_ascii=False)}"
                        if time.time() - float(getattr(self, "_last_openai_tool_ts", 0.0) or 0.0) < 4.0 and sig == str(getattr(self, "_last_openai_tool_sig", "") or ""):
                            continue
                        self._last_openai_tool_sig = sig
                        self._last_openai_tool_ts = time.time()
                        shim = _OpenAIToolCallShim(call.id, call.name, call.args)
                        try:
                            fr = asyncio.run(self._execute_tool(shim))
                            payload = getattr(fr, "response", None) or {}
                            if call.name in silent_tool_names:
                                continue
                            if isinstance(payload, dict):
                                item = str(payload.get("result") or "Done.")
                            else:
                                item = str(payload or "Done.")
                            if "stay completely silent" in item.lower() or "do not speak" in item.lower():
                                continue
                            summaries.append(item)
                        except Exception as exc:
                            summaries.append(f"{call.name} failed: {exc}")
                    spoken = re.sub(r"\s+", " ", " ".join(x for x in summaries if x)).strip()
                    if spoken:
                        self.ui.write_log("FRIDAY: " + spoken)
                        self._local_tts(spoken)
                else:
                    spoken = result.text.strip() or "Komutu anladım."
                    self.ui.write_log("FRIDAY: " + spoken)
                    self._local_tts(spoken)
            except Exception as exc:
                self.ui.write_log(f"ERR: OpenAI command failed — {exc}")
                traceback.print_exc()
            finally:
                if self.ui.standby:
                    self.ui.set_state("STANDBY")
                elif not self.ui.muted:
                    self.ui.set_state("LISTENING")

        threading.Thread(target=_worker, daemon=True, name="FridayOpenAICommand").start()
        return True

    def _drain_audio_queue(self):
        q = getattr(self, "audio_in_queue", None)
        if not q:
            return
        try:
            while True:
                q.get_nowait()
        except Exception:
            pass

    def _reset_live_runtime_state(self):
        """Reset transient queues/state before reconnecting a Live session."""
        self.session = None
        self._loop = None
        self._voice_local_handled = False
        self._suppress_model_audio_until = 0.0
        self.set_speaking(False)
        try:
            self._drain_audio_queue()
        except Exception:
            pass
        try:
            cancel_vision_requests()
        except Exception:
            pass

    def _suppress_model_output(self, seconds: float = 4.0):
        self._suppress_model_audio_until = max(
            float(getattr(self, "_suppress_model_audio_until", 0.0) or 0.0),
            time.time() + max(0.5, float(seconds or 0.5)),
        )
        self._drain_audio_queue()
        try:
            self.set_speaking(False)
        except Exception:
            pass

    def _camera_is_enabled(self) -> bool:
        try:
            if hasattr(self.ui, "camera_access_enabled"):
                return bool(self.ui.camera_access_enabled())
        except Exception:
            pass
        try:
            return bool(get_friday_camera_enabled())
        except Exception:
            return bool(globals().get("FRIDAY_CAMERA_ENABLED", True))

    def _camera_disabled_reply(self) -> str:
        try:
            if hasattr(self.ui, "camera_disabled_message"):
                msg = str(self.ui.camera_disabled_message() or "").strip()
                if msg:
                    return msg
        except Exception:
            pass
        try:
            return str(get_friday_camera_disabled_message())
        except Exception:
            return str(globals().get("FRIDAY_CAMERA_DISABLED_MESSAGE") or "Camera access is currently disabled in FRIDAY settings. I cannot open the camera until Camera Access is enabled.")

    def _refuse_camera_disabled(self) -> bool:
        msg = self._camera_disabled_reply()
        try:
            self.ui.write_log("FRIDAY: " + msg)
        except Exception:
            pass
        try:
            self.speak(msg)
        except Exception:
            pass
        return True

    def _is_camera_direct_command(self, text: str) -> str | None:
        t = self._norm_text(text)
        if not t:
            return None

        close_phrases = (
            "/camera-off", "/kamera-kapat",
            "kamerayi kapat", "kamerayı kapat",
            "kamera kapat", "kamera modunu kapat",
            "gorsel modu kapat", "görsel modu kapat",
            "vision mode off", "camera off", "close camera", "stop camera"
        )
        open_phrases = (
            "/camera", "/kamera",
            "kamerayi ac", "kamerayı aç",
            "kamera ac", "kamera aç",
            "kamera modunu ac", "kamera modunu aç",
            "gorsel moda gec", "görsel moda geç",
            "kamerayi kullan", "kamerayı kullan",
            "camera on", "open camera", "start camera", "vision mode"
        )

        if any(p in t for p in close_phrases):
            return "close"
        if any(p in t for p in open_phrases):
            return "open"
        return None

    def _looks_like_audio_status_request(self, text: str) -> bool:
        """True for hearing/microphone/speaker checks that must never open camera."""
        t = self._norm_text(text)
        if not t:
            return False
        audio_phrases = (
            "sesim geliyor mu", "sesimi duyuyor musun", "beni duyuyor musun",
            "sesimi aliyor musun", "sesimi alıyor musun", "ses geliyor mu",
            "sesin geliyor mu", "sesini duyuyor musun", "ses net mi",
            "sesim net mi", "mikrofon", "microphone", "mic",
            "duyuyor musun", "duyabiliyor musun", "beni duyabiliyor musun",
            "can you hear me", "do you hear me", "is my voice clear",
            "voice clear", "audio check", "sound check", "hear my voice",
            "asistanin sesini", "asistanın sesini", "sesini degerlendir",
            "sesini değerlendir", "ses kalitesi", "hoparlor", "hoparlör"
        )
        return any(p in t for p in audio_phrases)

    def _looks_like_camera_vision_request(self, text: str) -> bool:
        """Detect visual real-world questions before Gemini produces a wrong normal answer."""
        t = self._norm_text(text)
        if not t:
            return False

        # Audio/hearing checks are not visual questions. OpenAI Realtime can
        # hear the user without using the camera.
        if self._looks_like_audio_status_request(text):
            return False

        # Screen-specific questions must stay in normal tool flow / angle=screen.
        screen_words = ("ekran", "monitorde", "monitörde", "desktop", "sayfada", "pencerede")
        if any(w in t for w in screen_words):
            return False

        camera_phrases = (
            "elimde ne", "elinde ne", "ne tutuyorum", "ne tutuyorsun",
            "elimdekini", "elimdeki", "elime bak", "ellerime bak",
            "su an elimde", "şu an elimde", "suan elimde",
            "buna bak", "bunu goruyor", "bunu görüyor", "bunu tani", "bunu tanı",
            "ne gosteriyorum", "ne gösteriyorum", "gosteriyorum", "gösteriyorum",
            "kameraya bak", "kameradan bak", "kameradan gor", "kameradan gör",
            "beni goruyor", "beni görüyor", "ne goruyorsun", "ne görüyorsun",
            "onumde ne", "önümde ne", "masada ne", "odada ne",
            "what am i holding", "what is in my hand", "what do you see",
            "look at camera", "look through camera", "use camera", "webcam"
        )
        return any(p in t for p in camera_phrases)

    def _set_camera_mode_local(self, action: str, source: str = "local") -> bool:
        now = time.time()
        # A partial voice transcription can repeat the same phrase a few times.
        if now - float(getattr(self, "_last_camera_mode_command_ts", 0.0) or 0.0) < 1.2:
            return True
        self._last_camera_mode_command_ts = now

        action = (action or "open").lower().strip()
        if action != "close" and not self._camera_is_enabled():
            return self._refuse_camera_disabled()
        if action == "close":
            cancel_vision_requests()
            if hasattr(self.ui, "stop_camera_mode"):
                self.ui.stop_camera_mode()
            return True

        self.ui.write_log("SYS: Camera vision mode opening.")
        if hasattr(self.ui, "start_camera_mode"):
            self.ui.start_camera_mode(camera_index=None)
        return True

    def _start_direct_camera_vision(self, text: str, source: str = "voice") -> bool:
        if not self._camera_is_enabled():
            return self._refuse_camera_disabled()
        now = time.time()
        clean_text = (text or "Analyze what you see through the camera.").strip()
        norm_text = self._norm_text(clean_text)
        # Partial voice transcripts may repeat the exact same sentence. Ignore only ultra-fast duplicates,
        # but let a fresh camera command cancel the old analysis immediately.
        if (
            now - float(getattr(self, "_last_direct_camera_vision_ts", 0.0) or 0.0) < 1.0
            and norm_text == str(getattr(self, "_last_direct_camera_vision_text", "") or "")
        ):
            return True
        self._last_direct_camera_vision_ts = now
        self._last_direct_camera_vision_text = norm_text
        cancel_vision_requests()

        if hasattr(self.ui, "start_camera_mode"):
            self.ui.start_camera_mode(camera_index=None)
        self.ui.write_log("SYS: Camera vision mode opening; camera analysis started.")

        threading.Thread(
            target=screen_process,
            kwargs={
                "parameters": {"angle": "camera", "text": clean_text, "_camera_started": True, "_speak_callback": self._local_tts},
                "response": None,
                "player": self.ui,
                "session_memory": None,
            },
            daemon=True,
        ).start()
        return True

    def _mode_command_kind(self, text: str) -> str | None:
        """Detect hard local FRIDAY mode commands before any AI/tool routing.

        These commands must never be treated as normal computer_settings actions.
        They change FRIDAY's own microphone/listening state immediately.
        """
        t = self._norm_text(text)
        if not t:
            return None

        standby_phrases = (
            "/standby", "/bekleme",
            "standby", "standby mode", "standby mod", "stand by", "stand by mode", "stand by modu",
            "bekleme modu", "bekleme moduna", "bekleme modunu", "bekleme modunu aktif",
            "bekleme moduna gec", "bekleme moduna gir", "bekleme moduna al",
            "beklemeye gec", "beklemeye al", "beni beklemeye al",
            "dinlemeyi durdur", "sesli dinlemeyi durdur", "mikrofon dinlemeyi durdur",
            "uyku moduna gec", "uyku modu", "sleep mode", "go standby", "go to standby",
        )
        wake_phrases = (
            "/wake", "/dinle",
            "wake", "wake up", "wake friday", "wake medpov",
            "hey friday", "hey medpov", "hey med pov",
            "dinleme moduna gec", "dinleme modunu aktif", "dinlemeye gec",
            "beni dinle", "tekrar dinle", "aktif dinleme", "listening mode",
        )

        # Wake should win for explicit wake-word phrases such as "hey friday".
        if any(p in t for p in wake_phrases):
            return "wake"
        if any(p in t for p in standby_phrases):
            return "standby"
        return None

    def _handle_friday_mode_command(self, text: str, source: str = "text") -> bool:
        t = self._norm_text(text)
        if not t:
            return False

        camera_action = self._is_camera_direct_command(t)
        if camera_action:
            self._set_camera_mode_local(camera_action, source=source)
            return True

        mode_kind = self._mode_command_kind(t)

        if mode_kind == "standby":
            self.ui.set_standby(True)
            self.ui.write_log("SYS: Bekleme modu aktif. Yazılı komutlar çalışır; mikrofon girişi standby kapısına alındı.")
            return True

        if mode_kind == "wake":
            if self.ui.muted:
                self.ui.muted = False
            self.ui.set_standby(False)
            self.ui.write_log("SYS: Dinleme modu aktif.")
            return True

        return False

    def _handle_realtime_mode_tool_action(self, name: str, args: dict, source: str = "tool") -> str | None:
        """Catch model-routed standby/wake calls before computer_settings.

        In Realtime voice mode the model may incorrectly call:
        computer_settings({"action":"standby"}). That action is not an OS setting;
        it is FRIDAY's own runtime mode. Handle it here so the UI immediately turns
        orange and microphone audio is gated.
        """
        if str(name or "").strip() != "computer_settings":
            return None
        args = dict(args or {})
        merged = " ".join(
            str(args.get(k) or "")
            for k in ("action", "description", "value", "text", "command")
        ).strip()
        mode_kind = self._mode_command_kind(merged)
        if mode_kind == "standby":
            self._openai_local_mode_handled_until = time.time() + 2.5
            self._suppress_model_output(4.0)
            self._openai_realtime_stop_audio()
            self.ui.set_standby(True)
            return "Standby mode active. Stay completely silent. Do not call any other tool."
        if mode_kind == "wake":
            self._openai_local_mode_handled_until = time.time() + 1.0
            self._suppress_model_output(1.5)
            if self.ui.muted:
                self.ui.muted = False
            self.ui.set_standby(False)
            return "Listening mode active. Give a very short acknowledgement only if needed."
        return None


    def _parse_security_map_direct_command(self, text: str) -> dict | None:
        raw = (text or "").strip()
        t = self._norm_text(raw)
        if not t:
            return None

        # Hard map close commands.
        close_phrases = (
            "/map close", "/harita-kapat", "haritayi kapat", "haritayı kapat",
            "harita kapat", "map close", "close map", "security map kapat",
        )
        if any(p in t for p in close_phrases):
            return {"action": "map_close", "text": raw}

        map_open = False
        try:
            win = getattr(getattr(self.ui, "_win", None), "hud", None)
            map_open = bool(win and hasattr(win, "security_map_is_open") and win.security_map_is_open())
        except Exception:
            map_open = False

        # Layer commands: these must call the Security Center remote map API.
        has_map_word = any(w in t for w in ("harita", "map", "global map", "dunya", "dünya"))
        threat_words = ("son tehdit", "tehditleri", "tehditler", "threat", "attack", "saldiri", "saldırı")
        live_words = ("canli baglanti", "canlı bağlantı", "canli ziyaret", "canlı ziyaret", "live connection", "live visitor", "visitor", "user")
        both_words = ("both", "hepsi", "birlikte", "beraber", "tehdit ve canli", "tehdit ve canlı", "threat and live")
        if (has_map_word or map_open) and any(p in t for p in both_words):
            return {"action": "map_both", "live_range": "live", "include_curve_points": True, "text": raw}
        if (has_map_word or map_open) and any(p in t for p in threat_words):
            return {"action": "map_threat", "threat_range": "24h", "include_curve_points": True, "text": raw}
        if (has_map_word or map_open) and any(p in t for p in live_words):
            return {"action": "map_live", "live_range": "live", "include_curve_points": True, "text": raw}

        # Clean world map open commands.
        open_phrases = (
            "/map", "/harita", "harita ac", "harita aç", "haritayi ac", "haritayı aç",
            "dunya haritasi ac", "dünya haritası aç", "global harita ac", "global map open",
            "map open", "open map", "security map open", "security harita ac",
        )
        if any(p in t for p in open_phrases):
            return {"action": "map_open", "text": raw}

        # If the map is open, a known city/place phrase can directly focus it.
        known_places = (
            "turkiye", "türkiye", "turkey", "ankara", "izmir", "bursa", "antalya",
            "londra", "london", "istanbul", "new york", "tokyo", "tokio", "paris", "berlin", "dubai",
            "singapore", "sydney", "moscow", "moskova", "cairo", "kahire", "toronto", "amsterdam",
            "frankfurt", "los angeles", "san francisco", "hong kong", "mumbai", "delhi", "sao paulo",
        )
        if map_open or any(w in t for w in ("zoom", "odaklan", "odakla", "merkezle", "merkeze al", "center", "haritada", "mapte")):
            for place in known_places:
                if place in t:
                    return {"action": "map_zoom", "focus": place, "text": raw}

        return None

    def _handle_security_map_direct_command(self, text: str) -> bool:
        params = self._parse_security_map_direct_command(text)
        if not params:
            return False

        def _worker():
            try:
                self.ui.set_state("THINKING")
                result = security_center_action(parameters=params, player=self.ui, speak=self.speak)
                self.ui.write_log("FRIDAY: " + str(result))
                # Map mode is visual; keep speech short if this came from voice.
                try:
                    if not str(params.get("action", "")).endswith("close"):
                        self.speak(str(result).split("\n", 1)[0])
                except Exception:
                    pass
            except Exception as e:
                self.ui.write_log(f"ERR: Security map command failed — {e}")
            finally:
                if self.ui.standby:
                    self.ui.set_state("STANDBY")
                elif not self.ui.muted:
                    self.ui.set_state("LISTENING")

        threading.Thread(target=_worker, daemon=True).start()
        return True

    def _handle_security_center_direct_command(self, text: str) -> bool:
        raw = (text or "").strip()
        if not raw.lower().startswith(("/sc", "sc ", "security-center ")):
            return False
        def _worker():
            try:
                from tools.medpov_security_center_commands import parse_slash_command, security_center_action
                params = parse_slash_command(raw) or {"action": "overview", "text": raw}
                self.ui.set_state("THINKING")
                result = security_center_action(parameters=params, player=self.ui, speak=self.speak)
                self.ui.write_log("FRIDAY: " + str(result))
            except Exception as e:
                self.ui.write_log(f"ERR: Security Center command failed — {e}")
            finally:
                if self.ui.standby:
                    self.ui.set_state("STANDBY")
                elif not self.ui.muted:
                    self.ui.set_state("LISTENING")
        threading.Thread(target=_worker, daemon=True).start()
        return True

    def _on_text_command(self, text: str):
        # In full OpenAI Realtime mode, keep command flow inside OpenAI.
        # Only hard local mode commands remain immediate; visual questions are
        # routed to OpenAI so it can call screen_process and speak the result in
        # the same low-latency voice session.
        if self._handle_friday_mode_command(text, source="text"):
            self._suppress_model_output(2.5)
            return
        if self._handle_security_map_direct_command(text):
            self._suppress_model_output(2.5)
            return
        if self._handle_security_center_direct_command(text):
            return
        if bool(getattr(self, "_openai_realtime_mode", False)):
            raw = (text or "").strip()
            if raw:
                self.ui.write_log(f"You: {raw}")
                if not self._send_openai_text_turn(raw):
                    self.ui.write_log("ERR: OpenAI Realtime bağlantısı hazır değil.")
            return
        if self._looks_like_camera_vision_request(text):
            self._suppress_model_output(5.5)
            self._start_direct_camera_vision(text, source="text")
            return
        if self._use_openai_brain():
            self._suppress_model_output(6.0)
            self._handle_openai_text_command(text, source="text")
            return
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if self.ui.standby:
            self.ui.set_state("STANDBY")
            return
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if self.ui.standby:
            if text:
                self.ui.write_log(f"FRIDAY: {text}")
            return
        if bool(getattr(self, "_openai_realtime_mode", False)):
            self._openai_realtime_say(text)
            return
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()
        medpov_profile = _load_medpov_profile()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        lang_ctx = (
            "[RESPONSE LANGUAGE]\n"
            f"{FRIDAY_RESPONSE_LANGUAGE_INSTRUCTION}\n"
            "This rule has priority over the base prompt and over tool/model language drift.\n"
        )

        provider_ctx = (
            "[AI PROVIDER]\n"
            f"Selected provider: {FRIDAY_AI_PROVIDER_LABEL}. "
            "If OpenAI is selected, local runtime may route final user commands to OpenAI and suppress duplicate Gemini commentary.\n"
        )

        parts = [time_ctx, lang_ctx, provider_ctx]
        if medpov_profile:
            parts.append("MEDPOV permanent profile:\n" + medpov_profile)
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            # Native audio preview sessions are more stable without session_resumption.
            # Some reconnects can return 1008 when resumption is requested.
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=FRIDAY_VOICE_NAME
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[FRIDAY] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "friday_camera_mode":
                action = str(args.get("action") or "open").lower().strip()
                if action in ("close", "off", "stop", "kapat"):
                    self._suppress_model_output(3.0)
                    cancel_vision_requests()
                    if hasattr(self.ui, "stop_camera_mode"):
                        self.ui.stop_camera_mode()
                    result = "Camera vision mode closed. Stay silent."
                else:
                    if not self._camera_is_enabled():
                        self._suppress_model_output(2.0)
                        result = self._camera_disabled_reply()
                    else:
                        self._suppress_model_output(2.0)
                        if hasattr(self.ui, "start_camera_mode"):
                            self.ui.start_camera_mode(camera_index=None)
                        result = "Camera vision mode opened. Stay silent."

            elif name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "pc_workspace":
                r = await loop.run_in_executor(None, lambda: pc_workspace(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                angle = str(args.get("angle") or "screen").lower().strip()
                if angle == "camera" and not self._camera_is_enabled():
                    self._suppress_model_output(2.0)
                    result = self._camera_disabled_reply()
                elif angle == "camera" and (time.time() - float(getattr(self, "_last_direct_camera_vision_ts", 0.0) or 0.0)) < 4.5:
                    # If the local voice interceptor already started camera analysis,
                    # ignore Gemini's duplicate tool call for a few seconds.
                    self._suppress_model_output(7.0)
                    result = "Camera vision analysis is already running silently. Do not speak or add commentary."
                else:
                    if angle == "camera":
                        cancel_vision_requests()
                        if hasattr(self.ui, "start_camera_mode"):
                            started = self.ui.start_camera_mode(camera_index=None)
                            if started is False:
                                result = self._camera_disabled_reply()
                                raise RuntimeError(result)
                        args["_camera_started"] = True

                    threading.Thread(
                        target=screen_process,
                        kwargs={"parameters": {**args, "_speak_callback": self._local_tts}, "response": None,
                                "player": self.ui, "session_memory": None},
                        daemon=True
                    ).start()
                    result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "security_map":
                r = await loop.run_in_executor(None, lambda: security_center_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Security Center map command completed."

            elif name == "security_center":
                r = await loop.run_in_executor(None, lambda: security_center_action(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Security Center command completed."

            elif name == "shutdown_friday":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if self.ui.standby:
            self.ui.set_state("STANDBY")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[FRIDAY] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    def _clap_config(self) -> dict:
        try:
            cfg_path = Path(__file__).resolve().parent / "config" / "friday_wake.json"
            if cfg_path.exists():
                data = json.loads(cfg_path.read_text(encoding="utf-8") or "{}")
                return dict((data.get("double_clap") or {}))
        except Exception:
            pass
        return {}

    def _handle_standby_audio_gate(self, indata, raw_bytes: bytes, loop):
        """Runs inside sounddevice callback; keep it very light."""
        if not self.ui.standby or self.ui.muted:
            return
        try:
            cfg = self._clap_config()
            if cfg.get("enabled", True):
                threshold = float(cfg.get("threshold", 0.34))
                max_gap = float(cfg.get("max_gap_ms", 1250)) / 1000.0
                min_gap = float(cfg.get("min_gap_ms", 140)) / 1000.0
                cooldown = float(cfg.get("cooldown_ms", 1500)) / 1000.0

                try:
                    peak = float(abs(indata).max()) / 32768.0
                except Exception:
                    peak = 0.0

                now = time.monotonic()
                if peak >= threshold and (now - self._last_clap_time) >= min_gap:
                    self._last_clap_time = now
                    self._clap_hits = [x for x in self._clap_hits if now - x <= max_gap]
                    self._clap_hits.append(now)
                    if len(self._clap_hits) >= 2 and (now - self._clap_hits[-2]) <= max_gap and (now - self._clap_hits[-2]) >= min_gap:
                        self._clap_hits.clear()
                        self._last_clap_time = now + cooldown
                        loop.call_soon_threadsafe(lambda: self._wake_from_standby("double clap"))
        except Exception:
            pass

        # Optional offline wake-word path. No crash if Vosk/model is absent.
        try:
            if self._wake_audio_queue is not None:
                def _push_wake():
                    try:
                        self._wake_audio_queue.put_nowait(raw_bytes)
                    except asyncio.QueueFull:
                        pass
                loop.call_soon_threadsafe(_push_wake)
        except Exception:
            pass

    def _wake_from_standby(self, reason: str = "wake"):
        if self.ui.muted:
            self.ui.muted = False
        if self.ui.standby:
            self.ui.set_standby(False)
            self.ui.write_log(f"SYS: Wake detected ({reason}). Listening mode active.")

    async def _wake_word_worker(self):
        try:
            cfg_path = Path(__file__).resolve().parent / "config" / "friday_wake.json"
            cfg = {}
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8") or "{}")
            vosk_cfg = cfg.get("vosk") or {}
            if not vosk_cfg.get("enabled", True):
                return
            model_dir = Path(__file__).resolve().parent / str(vosk_cfg.get("model_dir", "models/vosk-model-small-tr-0.3"))
            if not model_dir.exists():
                return
            import vosk  # optional dependency
            model = await asyncio.to_thread(vosk.Model, str(model_dir))
            rec = vosk.KaldiRecognizer(model, SEND_SAMPLE_RATE)
            words = [self._norm_text(x) for x in (cfg.get("wake_words") or ["hey friday", "hey medpov", "hey med pov"])]
        except Exception:
            return

        while True:
            data = await self._wake_audio_queue.get()
            if not self.ui.standby or self.ui.muted:
                continue
            try:
                accepted = await asyncio.to_thread(rec.AcceptWaveform, data)
                raw = rec.Result() if accepted else rec.PartialResult()
                text = self._norm_text((json.loads(raw or "{}").get("text") or json.loads(raw or "{}").get("partial") or ""))
                if text and any(w in text for w in words):
                    self._wake_from_standby("wake word")
            except Exception:
                continue

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[FRIDAY] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                friday_speaking = self._is_speaking
            if self._is_assistant_audio_guard_active():
                friday_speaking = True
            if not friday_speaking and not self.ui.muted:
                data = indata.tobytes()
                if self.ui.standby:
                    self._handle_standby_audio_gate(indata, data, loop)
                    return
                def _safe_push():
                    try:
                        self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                    except asyncio.QueueFull:
                        pass
                loop.call_soon_threadsafe(_safe_push)

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[FRIDAY] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[FRIDAY] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[FRIDAY] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                # Hard echo gate for OpenAI mode: while OpenAI TTS is
                                # playing, ignore every STT fragment from Gemini. This
                                # fixes the speaker->mic loop where FRIDAY answers its
                                # own reply and then routes random tool commands.
                                if self._use_openai_brain() and self._is_assistant_audio_guard_active():
                                    in_buf = []
                                    continue
                                if self._looks_like_assistant_echo(txt):
                                    continue
                                in_buf.append(txt)
                                live_in = " ".join(in_buf).strip()
                                if self._looks_like_assistant_echo(live_in):
                                    in_buf = []
                                    continue

                                # Handle camera commands / visual questions as soon as the
                                # input transcript is visible, before Gemini's normal answer
                                # audio can continue saying the wrong thing.
                                if live_in and not self._voice_local_handled:
                                    if self._handle_friday_mode_command(live_in, source="voice-live"):
                                        self._voice_local_handled = True
                                        self._suppress_model_output(4.0)
                                    elif self._looks_like_camera_vision_request(live_in):
                                        self._voice_local_handled = True
                                        self._suppress_model_output(6.0)
                                        self._start_direct_camera_vision(live_in, source="voice-live")
                                    elif self._use_openai_brain():
                                        # Gemini Live is used only as the microphone transcription bridge here;
                                        # the final command is routed to OpenAI after turn_complete.
                                        self._voice_local_handled = True
                                        self._openai_voice_pending = True
                                        self._suppress_model_output(8.0)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in and self._use_openai_brain() and self._is_assistant_audio_guard_active():
                                full_in = ""
                                self._openai_voice_pending = False
                                self._voice_local_handled = False
                            if full_in and self._looks_like_assistant_echo(full_in):
                                full_in = ""
                                self._openai_voice_pending = False
                                self._voice_local_handled = False
                            if full_in:
                                full_norm = self._norm_text(full_in)
                                now_final = time.time()
                                if (
                                    full_norm
                                    and full_norm == str(getattr(self, "_last_voice_final_norm", "") or "")
                                    and now_final - float(getattr(self, "_last_voice_final_ts", 0.0) or 0.0) < 4.0
                                ):
                                    full_in = ""
                                else:
                                    self._last_voice_final_norm = full_norm
                                    self._last_voice_final_ts = now_final
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if self._openai_voice_pending:
                                    self._suppress_model_output(8.0)
                                    self._handle_openai_text_command(full_in, source="voice")
                                elif not self._voice_local_handled:
                                    if self._handle_friday_mode_command(full_in, source="voice"):
                                        self._voice_local_handled = True
                                        self._suppress_model_output(4.0)
                                    elif self._looks_like_camera_vision_request(full_in):
                                        self._voice_local_handled = True
                                        self._suppress_model_output(6.0)
                                        self._start_direct_camera_vision(full_in, source="voice")
                            in_buf = []
                            self._openai_voice_pending = False

                            full_out = " ".join(out_buf).strip()
                            if full_out and not self._is_model_audio_suppressed() and not self._voice_local_handled:
                                self.ui.write_log(f"FRIDAY: {full_out}")
                            out_buf = []
                            self._voice_local_handled = False

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[FRIDAY] 📞 {fc.name}")
                            if self._use_openai_brain():
                                # In OpenAI provider mode Gemini Live is only the
                                # microphone/transcription bridge. Letting Gemini
                                # execute tools too creates duplicate vision calls
                                # and wrong actions such as description/toggle_mute.
                                fn_responses.append(types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"result": "OpenAI provider handles command routing. Gemini tool call ignored silently.", "silent": True},
                                ))
                                continue
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[FRIDAY] ❌ Recv: {e}")
            # The Google Live WebSocket may occasionally close with 1011/1008.
            # Re-raise to let run() reconnect, but avoid flooding the console with
            # huge nested TaskGroup traces for known transport/API errors.
            msg = str(e)
            if "1011" not in msg and "1008" not in msg:
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[FRIDAY] 🔊 Play started")

        try:
            stream = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
            )
            stream.start()
        except Exception as e:
            print(f"[FRIDAY] ❌ Audio output disabled: {e}")
            self.ui.write_log("SYS: Audio output unavailable. FRIDAY continues in text/log mode.")
            while True:
                await self.audio_in_queue.get()
                self.set_speaking(False)

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                if self.ui.standby or self._is_model_audio_suppressed():
                    self.set_speaking(False)
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[FRIDAY] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run_openai_realtime(self):
        """Run FRIDAY with OpenAI Realtime only.

        This path intentionally does not create a Gemini Live session. It uses
        one OpenAI websocket for microphone input, reasoning/tool calls, and
        streamed voice output, which removes the v2.7.x Gemini-STT -> OpenAI ->
        TTS bridge latency and echo loop.
        """
        try:
            import websockets  # type: ignore
        except Exception as exc:
            self.ui.write_log("ERR: websockets paketi eksik. Çalıştır: pip install websockets")
            raise RuntimeError("websockets package is missing") from exc

        api_key = (get_openai_api_key() or os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            self.ui.write_log("ERR: OpenAI API key eksik. Ayarlar > OpenAI alanından ekle.")
            raise RuntimeError("OpenAI API key is empty")

        self._openai_realtime_mode = True
        model = self._openai_realtime_model()
        url = "wss://api.openai.com/v1/realtime?model=" + quote_plus(model)
        headers = {"Authorization": "Bearer " + api_key}

        while True:
            try:
                print("[OpenAI RT] 🔌 Connecting...")
                print(f"[OpenAI RT] 🎙 Voice loaded: {self._openai_realtime_voice()} | Model: {model} | Provider: OpenAI Realtime")
                self.ui.set_state("THINKING")
                schema = str(getattr(self, "_openai_realtime_schema", "ga") or "ga")
                request_headers = dict(headers)
                if schema == "beta":
                    request_headers["OpenAI-Beta"] = "realtime=v1"
                async with websockets.connect(
                    url,
                    additional_headers=request_headers,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=8 * 1024 * 1024,
                    max_queue=64,
                ) as ws:
                    self._openai_ws = ws
                    self._openai_loop = asyncio.get_event_loop()
                    self._openai_send_queue = asyncio.Queue(maxsize=80)
                    self._openai_audio_queue = asyncio.Queue(maxsize=600)
                    self._openai_turn_done_event = asyncio.Event()
                    self.audio_in_queue = self._openai_audio_queue
                    self.out_queue = self._openai_send_queue
                    self.session = None
                    self._loop = self._openai_loop
                    self._wake_audio_queue = asyncio.Queue(maxsize=8)
                    self._openai_function_args = {}
                    self._openai_function_names = {}
                    self._openai_executed_tool_calls = set()
                    self._openai_response_active = False
                    self._openai_active_response_id = ""
                    self._openai_pending_response_after_tool = False
                    self._openai_audio_bytes_seen = 0
                    self._openai_audio_chunks_seen = 0
                    self._openai_audio_bytes_played = 0
                    self._openai_user_turn_id = 0
                    self._openai_current_turn_tools = set()
                    self._openai_camera_turn_id = -1
                    self._openai_last_camera_result = ""
                    self._openai_audio_drain_reports = set()
                    self._openai_session_update_ok = False
                    self._openai_session_update_retry = 0

                    await ws.send(json.dumps(
                        self._openai_realtime_session_update(legacy=(schema == "beta")),
                        ensure_ascii=False,
                    ))
                    print("[OpenAI RT] ✅ Connected.")
                    self.ui.set_state("STANDBY" if self.ui.standby else "LISTENING")
                    self.ui.write_log("SYS: MEDPOV FRIDAY online.")
                    self.ui.write_log("SYS: OpenAI Realtime provider online.")

                    # No Gemini vision warmup in OpenAI mode. screen_process uses
                    # OpenAI Vision directly when the provider is OpenAI.
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._openai_ws_send_loop(ws))
                        tg.create_task(self._openai_listen_audio())
                        tg.create_task(self._openai_recv_loop(ws))
                        tg.create_task(self._openai_play_audio())
                        tg.create_task(self._wake_word_worker())

            except BaseExceptionGroup as eg:
                for exc in eg.exceptions:
                    print(f"[OpenAI RT] ⚠️ realtime task stopped: {exc}")
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
            except Exception as exc:
                print(f"[OpenAI RT] ⚠️ {exc}")
                traceback.print_exc()
            finally:
                self._openai_ws = None
                self._openai_send_queue = None
                self._openai_audio_queue = None
                self._openai_loop = None
                self._openai_turn_done_event = None
                self._openai_function_args = {}
                self._openai_function_names = {}
                self._openai_executed_tool_calls = set()
                self._openai_response_active = False
                self._openai_active_response_id = ""
                self._openai_pending_response_after_tool = False
                self._openai_audio_bytes_seen = 0
                self._openai_audio_chunks_seen = 0
                self._openai_audio_bytes_played = 0
                self._openai_session_update_ok = False
                self._openai_session_update_retry = 0
                self._openai_realtime_stop_audio()
                try:
                    cancel_vision_requests()
                except Exception:
                    pass
            self.ui.set_state("THINKING")
            print("[OpenAI RT] 🔄 Reconnecting in 2s...")
            await asyncio.sleep(2)

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[FRIDAY] 🔌 Connecting...")
                print(f"[FRIDAY] 🎙 Voice loaded: {FRIDAY_VOICE_NAME} | Model: {_live_model_name()} | Provider: {FRIDAY_AI_PROVIDER_LABEL}")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=_live_model_name(), config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._wake_audio_queue = asyncio.Queue(maxsize=8)
                    self._turn_done_event = asyncio.Event()

                    print("[FRIDAY] ✅ Connected.")
                    self.ui.set_state("STANDBY" if self.ui.standby else "LISTENING")
                    self.ui.write_log("SYS: MEDPOV FRIDAY online.")

                    # Warm up the separate Vision Live session in the background.
                    # First camera analysis is much faster after this.
                    threading.Thread(
                        target=warmup_session,
                        kwargs={"player": self.ui},
                        daemon=True,
                        name="FRIDAYVisionWarmup",
                    ).start()

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._wake_word_worker())

            except BaseExceptionGroup as eg:
                # TaskGroup wraps websocket/API failures here. Keep the app alive and reconnect.
                for exc in eg.exceptions:
                    msg = str(exc)
                    print(f"[FRIDAY] ⚠️ Live task stopped: {msg}")
                    if "1011" not in msg and "1008" not in msg:
                        traceback.print_exception(type(exc), exc, exc.__traceback__)
            except Exception as e:
                msg = str(e)
                print(f"[FRIDAY] ⚠️ {msg}")
                if "1011" not in msg and "1008" not in msg:
                    traceback.print_exc()
            self._reset_live_runtime_state()
            self.ui.set_state("THINKING")
            print("[FRIDAY] 🔄 Reconnecting in 2s...")
            await asyncio.sleep(2)

def main():
    ui = FridayUI("face.png")

    def runner():
        ui.wait_for_api_key()
        friday = FridayLive(ui)
        try:
            if friday._use_openai_realtime():
                asyncio.run(friday.run_openai_realtime())
            else:
                asyncio.run(friday.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
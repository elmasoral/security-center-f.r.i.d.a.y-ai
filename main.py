import asyncio
import re
import threading
import json
import sys
import traceback
import time
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
try:
    from google.genai import errors as genai_errors
except Exception:
    genai_errors = None
from ui import JarvisUI
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
    )
    FRIDAY_SETTINGS = bootstrap_environment()
    FRIDAY_VOICE_NAME = get_friday_voice_name()
    FRIDAY_SPEECH_CONFIG = get_speech_config()
    FRIDAY_GEMINI_MODEL = get_gemini_model()
    FRIDAY_RESPONSE_LANGUAGE = get_friday_response_language()
    FRIDAY_RESPONSE_LANGUAGE_INSTRUCTION = get_friday_response_language_instruction()
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
# --- /MEDPOV FRIDAY runtime settings bridge ---





def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
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
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
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
            "Connects to the live MEDPOV Security Center and reads or manages threats, events, IP profiles, traffic, live sessions, bots, login pressure, health reports, and IP rules. "
            "Use this whenever the user asks about Security Center, threats, attacks, malicious IPs, bot/scanner events, blocked requests, incident analysis, or wants to block/allow/ignore an IP. "
            "If the user asks to research an IP on the internet, first call this tool for Security Center context, then use web_search with the returned research queries if needed."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "overview | threats | events | event | ip_profile | analyze | traffic | live | bots | login | health | settings | capabilities | block_ip | allow_ip | ignore_ip | resolve_event | resolve_ip_events | ai_recheck"},
                "ip": {"type": "STRING", "description": "IP address for ip_profile/analyze/block/allow/ignore/traffic"},
                "event_id": {"type": "INTEGER", "description": "Security event ID for event/analyze/resolve_event"},
                "risk": {"type": "STRING", "description": "Optional risk filter: LOW | MEDIUM | HIGH | CRITICAL"},
                "limit": {"type": "INTEGER", "description": "Number of records to return"},
                "hours": {"type": "INTEGER", "description": "Lookback period in hours"},
                "minutes": {"type": "INTEGER", "description": "Duration for temporary IP block"},
                "reason": {"type": "STRING", "description": "Reason for write actions"},
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

class JarvisLive:

    def __init__(self, ui: JarvisUI):
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

    def _norm_text(self, text: str) -> str:
        text = (text or "").lower().strip()
        repl = str.maketrans({"ı":"i", "ğ":"g", "ü":"u", "ş":"s", "ö":"o", "ç":"c"})
        text = text.translate(repl)
        text = re.sub(r"\s+", " ", text)
        return text

    def _is_model_audio_suppressed(self) -> bool:
        return time.time() < float(getattr(self, "_suppress_model_audio_until", 0.0) or 0.0)

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

    def _looks_like_camera_vision_request(self, text: str) -> bool:
        """Detect visual real-world questions before Gemini produces a wrong normal answer."""
        t = self._norm_text(text)
        if not t:
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
        if action == "close":
            cancel_vision_requests()
            if hasattr(self.ui, "stop_camera_mode"):
                self.ui.stop_camera_mode()
            return True

        self.ui.write_log("SYS: Görsel moda geçiyorum.")
        if hasattr(self.ui, "start_camera_mode"):
            self.ui.start_camera_mode(camera_index=None)
        return True

    def _start_direct_camera_vision(self, text: str, source: str = "voice") -> bool:
        now = time.time()
        clean_text = (text or "Kameradan gördüğünü analiz et.").strip()
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
        self.ui.write_log("SYS: Görsel moda geçiyorum; kamera analizi başlatıldı.")

        threading.Thread(
            target=screen_process,
            kwargs={
                "parameters": {"angle": "camera", "text": clean_text, "_camera_started": True},
                "response": None,
                "player": self.ui,
                "session_memory": None,
            },
            daemon=True,
        ).start()
        return True

    def _handle_friday_mode_command(self, text: str, source: str = "text") -> bool:
        t = self._norm_text(text)
        if not t:
            return False

        camera_action = self._is_camera_direct_command(t)
        if camera_action:
            self._set_camera_mode_local(camera_action, source=source)
            return True

        standby_phrases = (
            "/standby", "/bekleme", "standby", "standby mode",
            "bekleme moduna gec", "beklemeye gec", "beklemeye al",
            "dinlemeyi durdur", "sesli dinlemeyi durdur", "uyku moduna gec"
        )
        wake_phrases = (
            "/wake", "/dinle", "wake", "wake up",
            "hey friday", "hey medpov", "hey med pov",
            "dinleme moduna gec", "dinlemeye gec", "beni dinle", "tekrar dinle"
        )

        if any(p in t for p in standby_phrases):
            self.ui.set_standby(True)
            self.ui.write_log("SYS: Bekleme modu aktif. Yazılı komutlar çalışır; Gemini mikrofon girişi durduruldu.")
            return True

        if any(p in t for p in wake_phrases):
            if self.ui.muted:
                self.ui.muted = False
            self.ui.set_standby(False)
            self.ui.write_log("SYS: Dinleme modu aktif.")
            return True

        return False


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
                if not self.ui.muted: self.ui.set_state("LISTENING")
        threading.Thread(target=_worker, daemon=True).start()
        return True

    def _on_text_command(self, text: str):
        if self._handle_friday_mode_command(text, source="text"):
            self._suppress_model_output(2.5)
            return
        if self._looks_like_camera_vision_request(text):
            self._suppress_model_output(5.5)
            self._start_direct_camera_vision(text, source="text")
            return
        if self._handle_security_center_direct_command(text):
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

        parts = [time_ctx, lang_ctx]
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

                # If the local voice interceptor already started camera analysis,
                # ignore Gemini's duplicate tool call for a few seconds.
                if angle == "camera" and (time.time() - float(getattr(self, "_last_direct_camera_vision_ts", 0.0) or 0.0)) < 4.5:
                    self._suppress_model_output(7.0)
                    result = "Camera vision analysis is already running silently. Do not speak or add commentary."
                else:
                    if angle == "camera":
                        cancel_vision_requests()
                        if hasattr(self.ui, "start_camera_mode"):
                            self.ui.start_camera_mode(camera_index=None)
                        args["_camera_started"] = True

                    threading.Thread(
                        target=screen_process,
                        kwargs={"parameters": args, "response": None,
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
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
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
                                in_buf.append(txt)
                                live_in = " ".join(in_buf).strip()

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

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if not self._voice_local_handled:
                                    if self._handle_friday_mode_command(full_in, source="voice"):
                                        self._voice_local_handled = True
                                        self._suppress_model_output(4.0)
                                    elif self._looks_like_camera_vision_request(full_in):
                                        self._voice_local_handled = True
                                        self._suppress_model_output(6.0)
                                        self._start_direct_camera_vision(full_in, source="voice")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out and not self._is_model_audio_suppressed() and not self._voice_local_handled:
                                self.ui.write_log(f"FRIDAY: {full_out}")
                            out_buf = []
                            self._voice_local_handled = False

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[FRIDAY] 📞 {fc.name}")
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

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[FRIDAY] 🔌 Connecting...")
                print(f"[FRIDAY] 🎙 Voice loaded: {FRIDAY_VOICE_NAME} | Model: {_live_model_name()}")
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
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
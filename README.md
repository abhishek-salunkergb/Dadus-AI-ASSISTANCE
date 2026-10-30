# DADUS - Personal AI Operating Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078d4.svg)](https://www.microsoft.com/windows/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **DADUS** (pronounced *Dah-doos*) is a production-quality personal AI operating assistant designed from first principles for natural voice and desktop interaction on Windows, engineered with a decoupled architecture ready to seamlessly connect mobile clients (Android) and Model Context Protocol (MCP) tool servers.

---

## 1. DADUS Overview

Unlike basic chatbot wrappers or rigid if/else rule systems, DADUS implements a real autonomous AI agent architecture:

```
Voice Input ──► STT ──► Agent Brain ──► Intent & Tool Router ──► Permission Guard ──► Execution ──► Response ──► TTS
```

DADUS perceives speech via microphone, understands intent via structured tool selection, evaluates safety through a 3-tier permission security layer, executes desktop actions natively, and responds with natural voice speech and a responsive glassmorphic UI.

**Product Identity:**
- **Project Name:** DADUS
- **Assistant Name:** Dadus
- **Wake Phrase:** `"Hey Dadus"`
- **Personality:** Respectful, concise, natural, focused. Addresses the user as "boss". Example: *"Done, boss."*, *"Opening Spotify and playing Believer."*

---

## 2. Features

- **Natural Language Tool Selection:** Understands different phrasings (*"Open Chrome"*, *"Launch Chrome"*, *"Can you bring up Google Chrome?"* or *"Open my code editor"*) and maps them into structured parameter calls.
- **Windows Desktop Application Detection:** Scans the Windows Registry, Start Menu (`.lnk` shortcuts), and system PATH dynamically to resolve installed applications (Google Chrome, VS Code, Cursor, Spotify, Notepad, Calculator, Edge, etc.).
- **Smart Music Routing & Disambiguation:**
  - *"Play Believer."* ➔ Detects available music apps (Spotify, YouTube). If neither is specified and no preference is saved, Dadus asks: *"Boss, I found Spotify and YouTube. Which one should I use?"*
  - Follow-up *"Spotify"* ➔ *"Opening Spotify and playing Believer."*
  - Preference saved in memory ➔ Executes directly without asking.
- **Multi-Tier Security & Permission Guard:**
  - **SAFE:** Auto-executed (open apps, set volume, play music, web search, screenshots, time, schedule).
  - **CONFIRMATION REQUIRED:** Destructive actions (deleting files/folders, shutting down) pause and require explicit user consent (*"Boss, this will permanently delete 'X'. Should I continue?"*).
  - **RESTRICTED:** Passwords, banking credentials, OS authentication bypass, and disabling antivirus are permanently blocked at the code level, regardless of prompt-injection attempts.
- **Zero-Latency Offline Voice Stack:**
  - **TTS:** Windows native `SAPI.SpVoice` (instant, offline, zero cloud API cost) + OpenAI cloud TTS option.
  - **STT:** `SpeechRecognition` (Google Web Speech / Whisper) with automatic PyAudio and microphone fallbacks.
  - **Wake Word:** Continuous background listener for *"Hey Dadus"* + Push-to-Talk button.
- **Persistent SQLite Memory & Schedule:**
  - Remembers user preferences (*"Remember that I prefer Spotify"*, *"Forget that I prefer Spotify"*).
  - Natural time reminder parser (*"Remind me at 7 PM to study Python"*).
  - Daily schedule manager (*"What is my schedule today?"*, *"Add Gym at 5 PM"*).
- **Windows System Tools:** Hardware audio volume adjustment (0-100%) and mute via `pycaw`, desktop screenshots via Pillow, screen locking via Windows API, and CPU/RAM/Battery hardware metrics via `psutil`.
- **Modern Glassmorphic Desktop Web UI:** Live audio visualizer waves, status badges, Push-to-Talk, conversation logs, confirmation modals, schedule manager, and memory inspector.

---

## 3. Architecture

```mermaid
flowchart TD
    User([User Voice / Text]) --> VoiceIn[Wake Word Engine / Microphone]
    VoiceIn --> STT[Speech-to-Text: SpeechRecognition / Whisper]
    STT --> Agent[Agent Brain: DadusAgent]
    Agent --> Router[Intent Router: LLM Tool Calling / Semantic Fallback]
    Router --> Security{Permission Layer}
    
    Security -->|SAFE| Registry[Tool Registry]
    Security -->|CONFIRMATION REQUIRED| ConfirmMgr[Confirmation Manager]
    ConfirmMgr -->|Awaiting Consent| Agent
    ConfirmMgr -->|User Confirmed| Registry
    Security -->|RESTRICTED| Blocked[Blocked: "Credentials protected"]
    Blocked --> Agent
    
    Registry --> AppTools[App Tools: Chrome, VS Code, etc.]
    Registry --> MusicTools[Music Tools: Spotify, YouTube]
    Registry --> SystemTools[System Tools: Volume, Screenshots, Lock]
    Registry --> PersonalTools[Personal Tools: Reminders, Schedule, Memory]
    
    AppTools --> Result[Tool Result]
    MusicTools --> Result
    SystemTools --> Result
    PersonalTools --> Result
    
    Result --> Agent
    Agent --> AuditLog[(SQLite Audit Log & Memory)]
    Agent --> TTS[Text-to-Speech: Windows SAPI / OpenAI]
    TTS --> AudioOut([Speaker Audio & Web UI])
```

---

## 4. Project Structure

```
DADUS/
│
├── app/
│   ├── __init__.py                # Package root & constants
│   ├── main.py                    # Entry point & CLI/Voice/Web runner
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py            # Pydantic BaseSettings & centralized config
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py            # SQLite engine & session management
│   │   └── models.py              # Reminder, ScheduleItem, MemoryItem, AuditLog
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── permissions.py         # 3-tier permission evaluation & sanitizer
│   │   ├── confirmations.py       # Pending confirmation state machine
│   │   └── identity.py            # Speaker profile & verification interface
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── memory.py              # SQLite key-value preference store
│   │   └── retrieval.py           # Context retrieval for prompts
│   │
│   ├── tools/
│   │   ├── __init__.py            # Tool registration pipeline
│   │   ├── base.py                # BaseTool, ToolResult schemas
│   │   ├── registry.py            # Central registry & audit execution
│   │   ├── apps.py                # Windows app detection, open & close
│   │   ├── browser.py             # Controlled browser search & URL tools
│   │   ├── music.py               # Spotify & YouTube playback routing
│   │   ├── system.py              # Volume, screenshot, time, status, lock
│   │   ├── files.py               # File search & Recycle Bin deletion
│   │   ├── reminders.py           # Natural-time reminder manager
│   │   ├── schedule.py            # Daily schedule & calendar events
│   │   └── memory_tools.py        # store_memory & forget_memory tools
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py               # Central DadusAgent controller
│   │   ├── router.py              # LLM tool caller & semantic parser
│   │   ├── prompts.py             # System prompt & DADUS personality
│   │   └── state.py               # Multi-turn session & clarification tracking
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── stt.py                 # SpeechRecognition & Whisper STT
│   │   ├── tts.py                 # Native Windows SAPI & OpenAI TTS
│   │   └── wakeword.py            # Wake-word detection & push-to-talk
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── server.py              # FastAPI server (Web UI & future Android)
│   │
│   └── ui/
│       ├── __init__.py
│       ├── web_ui.py              # Desktop window launcher
│       └── static/
│           ├── index.html         # Responsive glassmorphic UI
│           ├── style.css          # Modern dark theme & animations
│           └── app.js             # Client controller & audio player
│
├── tests/
│   ├── conftest.py                # Pytest fixtures & environment setup
│   ├── test_acceptance_scenarios.py # 10 core acceptance tests from spec
│   ├── test_tools.py              # Unit tests for tools & schemas
│   ├── test_apps_music.py         # App detection & music workflow tests
│   ├── test_security.py           # Permission & injection resistance tests
│   ├── test_memory_schedule.py    # Memory, reminder & schedule tests
│   └── test_api.py                # FastAPI endpoint integration tests
│
├── data/                          # SQLite database, screenshots, audio
├── logs/                          # dadus.log audit trail
├── .env.example                   # Environment configuration template
├── .gitignore                     # Git ignore rules
├── requirements.txt               # Locked production dependencies
├── README.md                      # Comprehensive documentation
└── run.py                         # Single CLI runner
```

---

## 5. Installation

### Prerequisites
- Windows 10 or Windows 11 (64-bit)
- Python 3.10 or 3.11+
- Working microphone and speaker / headphones

### Clone & Install
```bash
git clone https://github.com/your-username/DADUS.git
cd DADUS

# Create virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 6. Environment Setup

Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```

Edit `.env` to configure your preferred settings:
```ini
# LLM Provider Configuration (OpenAI or OpenAI-compatible)
OPENAI_API_KEY=your_openai_or_groq_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.2

# Speech-to-Text (STT)
STT_PROVIDER=speech_recognition
STT_LANGUAGE=en-US

# Text-to-Speech (TTS)
# "sapi" uses the built-in Windows voice engine (instant, zero cost, completely offline!)
TTS_PROVIDER=sapi
TTS_ENABLED=true
TTS_VOICE_RATE=1
TTS_VOICE_VOLUME=100

# Wake-word Engine
WAKEWORD_PROVIDER=keyword
```

> **Note:** DADUS works **100% offline out-of-the-box** even without an API key thanks to its built-in semantic intent parser and native Windows SAPI voice engine! Adding an `OPENAI_API_KEY` enables arbitrary conversational reasoning.

---

## 7. Running DADUS

You can run DADUS in several modes:

### 1. Web & Desktop UI Mode (Default)
Starts the FastAPI server and launches the glassmorphic desktop interface in your browser:
```bash
python run.py
```
Open `http://127.0.0.1:8000` to interact.

### 2. Interactive CLI Mode
Interact with DADUS via terminal while hearing responses spoken aloud:
```bash
python run.py --cli
```

### 3. Continuous Voice Wake-Word Mode
Actively listens through your microphone for `"Hey Dadus"`:
```bash
python run.py --voice
```

### 4. Dedicated Native Window Mode
Opens DADUS inside a standalone desktop window (via `pywebview`):
```bash
python run.py --window
```

---

## 8. Voice Setup

DADUS supports two modes of voice interaction:

1. **Push-to-Talk (Recommended for quiet or noisy environments):**
   - Click the microphone button in the web interface or call `POST /api/voice/listen`.
   - DADUS records your command, transcribes it, and responds with voice.
2. **Continuous Wake-Word Detection:**
   - In `--voice` mode, DADUS runs a background audio listener calibrated for `"Hey Dadus"`.
   - Example: *"Hey Dadus, open Chrome."* ➔ Triggers and launches Chrome.

---

## 9. Adding an LLM Provider

DADUS supports any OpenAI-compatible API endpoint (OpenAI, Groq, Ollama, DeepSeek, vLLM, or Gemini's OpenAI compatibility endpoint).

### Example: Using Groq (Ultra-fast inference)
```ini
OPENAI_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

### Example: Using Local Ollama (Completely offline LLM)
```ini
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.2
```

---

## 10. Adding a New Tool

All tools inherit from `BaseTool` in [`app/tools/base.py`](file:///c:/Dadus%20AI%20Agent/app/tools/base.py) and are registered in [`app/tools/__init__.py`](file:///c:/Dadus%20AI%20Agent/app/tools/__init__.py).

### Example: Creating a Weather Tool
```python
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel

class WeatherInput(BaseModel):
    city: str = Field(description="City name, e.g. 'London'")

class WeatherTool(BaseTool):
    name = "get_weather"
    description = "Retrieves the current weather forecast for a city."
    permission_level = PermissionLevel.SAFE
    args_schema = WeatherInput

    def execute(self, city: str) -> ToolResult:
        # Fetch weather data...
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Boss, it is 22°C and sunny in {city}."
        )
```
Register the tool in `register_default_tools()` in `app/tools/__init__.py`:
```python
registry.register(WeatherTool())
```
DADUS will automatically:
1. Generate an OpenAI tool schema for the LLM.
2. Generate an MCP schema for future protocol exposure.
3. Enforce permission checks before execution.
4. Record structured audit logs in SQLite.

---

## 11. Permission System & Security Model

DADUS enforces a strict **3-Tier Permission Model** implemented entirely in application code (not just system prompts), ensuring that prompt injections cannot override system safety:

| Level | Behavior | Examples |
|---|---|---|
| **`SAFE`** | Executes immediately without interruption. | Open/close apps, play music, set volume, take screenshot, time, read schedule, store memory. |
| **`CONFIRMATION_REQUIRED`** | Pauses execution and asks for explicit confirmation. | Deleting files/folders, moving large numbers of files, system shutdown/restart. |
| **`RESTRICTED`** | Permanently blocked at code level. Returns polite denial. | Passwords, bank/credit card numbers, OS authentication bypass, disabling antivirus. |

### Confirmation Workflow Example
```
User: "Hey Dadus, delete this folder."
Dadus: "Boss, this will permanently delete 'C:\path\to\folder'. Should I continue?"
[Status: WAITING_CONFIRMATION]

User: "Yes." (or clicks UI "Confirm" button)
Dadus: "Successfully moved 'folder' to the Recycle Bin, boss."
```

---

## 12. Memory & Preference System

DADUS includes persistent SQLite memory to learn user habits:
- *"Remember that I prefer Spotify."* ➔ Stored as `preferred_music_app: Spotify`.
- Subsequent *"Play Believer."* ➔ Directly selects Spotify without asking for clarification.
- *"Forget that I prefer Spotify."* ➔ Clears the memory.
- All memories are inspectable and deletable in the UI "Memories & Prefs" tab.

---

## 13. Running Automated Tests

Run the full pytest suite:
```bash
python -m pytest -v
```

All 39 automated tests cover:
- Tool registration, OpenAI schemas, and MCP schemas.
- Windows application detection and path resolution.
- Opening and closing apps.
- Music intent, Spotify preference, and multi-app clarification.
- SAFE, CONFIRMATION_REQUIRED, and RESTRICTED permissions.
- Interactive confirmation workflows (accept and reject).
- SQLite memory, natural-time reminders, and daily schedule CRUD.
- Prompt injection resistance against credential queries and system directory deletion.
- FastAPI REST endpoints.
- **All 10 acceptance test scenarios from Section 30.**

---

## 14. Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| `Microphone access error` or `Could not find PyAudio` | Missing audio driver or PyAudio | Run `pip install pyaudio`. On Windows, pre-built wheels install automatically. |
| Windows SAPI voice sounds robotic | Default system voice selected | In Windows Settings ➔ *Time & Language* ➔ *Speech*, select *Microsoft David* or *Microsoft Zira*. |
| App not found when asking to open | App name differs from Start Menu shortcut | Use the exact name or alias (e.g. "VS Code" maps to "Visual Studio Code"). DADUS scans `.lnk` shortcuts and registry. |
| Spotify doesn't play directly | Spotify desktop client not running | DADUS opens the Spotify URI search or Spotify Web player cleanly without claiming false success. |

---

## 15. Future Android Architecture

DADUS was architected so an Android client can connect to the existing core without rewriting the backend:

```
┌──────────────────────────────────────────────┐
│           Android Mobile Device              │
│  - Android SpeechRecognizer (Google STT)     │
│  - Android TextToSpeech (Native TTS)         │
│  - Biometric Authentication (Fingerprint)    │
│  - Retrofit / OkHttp REST Client             │
└──────────────────────┬───────────────────────┘
                       │ HTTPS / WSS Authenticated API
                       ▼
┌──────────────────────────────────────────────┐
│             DADUS Backend                    │
│  - FastAPI REST Endpoints (/api/chat, etc.)  │
│  - DadusAgent Brain & Intent Router          │
│  - Permission Layer & Confirmation State     │
│  - SQLite Database (Reminders, Schedule)     │
└──────────────────────┬───────────────────────┘
                       ▼
         ┌────────────────────────────┐
         │       Target Devices       │
         │  - Laptop (Windows Tools)  │
         │  - Phone (Android Intents) │
         └────────────────────────────┘
```

1. **Clean Decoupling:** The Agent core and Tool Registry have zero dependency on the desktop UI.
2. **Authenticated API:** The Android app sends commands to `POST /api/chat` with an authorization bearer token.
3. **Native Mobile Execution:** Mobile-specific tools (e.g. `call_contact`, `send_sms`) will register under the same `BaseTool` abstraction and execute via official Android APIs.
4. **No Security Bypasses:** Adheres strictly to Android permissions and never attempts lock-screen bypasses.

---

## 15. Model Context Protocol (MCP) Server Integration

DADUS provides a fully standards-compliant **Model Context Protocol (MCP)** server operating via JSON-RPC 2.0 over standard I/O and programmatic interfaces:

- **Protocol Version:** `2024-11-05`
- **Exposed Methods:**
  - `initialize`: Performs client handshake, reports server capabilities, and identifies `dadus-mcp-server v1.0.0`.
  - `ping`: Standard MCP healthcheck endpoint.
  - `tools/list`: Dynamically exports all 29 approved DADUS tools formatted according to MCP JSON Schema specification.
  - `tools/call`: Dispatches requests through the central DADUS Permission Layer and execution registry with strict argument validation.

### Running DADUS MCP Server

Launch the MCP server in standard input/output mode:
```powershell
python -m app.mcp.server
```

Connect using the included programmatic client in Python:
```python
from app.mcp.client import MCPClient

client = MCPClient()
init_res = client.initialize()
tools = client.list_tools()
result = client.call_tool("get_current_time", {})
print(result)
```

---

## 16. Multi-Device & Mobile Architecture

DADUS incorporates a decoupled multi-device management system in `app/devices/`:

- **Device Registry:** Tracks connected clients (`windows_desktop`, `android_mobile`, `web_client`, `mcp_client`).
- **Capability Routing:** Validates whether a target device has specific capabilities (e.g. `SCREEN_CAPTURE`, `HARDWARE_MEDIA_KEYS`, `AUDIO_PLAYBACK`) before dispatching actions.
- **REST Endpoints:**
  - `GET /api/devices`: List all registered devices and their active capabilities.
  - `POST /api/devices/register`: Register new mobile or remote client endpoints with authentication tokens.

---

## 17. Phase 3 Acceptance Test Verification Matrix

All 10 Phase 3 Acceptance Scenarios have automated test coverage verified via `pytest`:

| Scenario | User Command | Expected Execution | Test Verification |
|---|---|---|---|
| **1** | `"Remember that I prefer Spotify."` | Stores `preferred_music_app="Spotify"` with category `preference` | ✅ PASSED (`test_scenario_1_and_2_memory_preference_and_recall`) |
| **2** | `"What music app do I prefer?"` | Recalls stored preference: *"Boss, you prefer Spotify."* | ✅ PASSED (`test_scenario_1_and_2_memory_preference_and_recall`) |
| **3** | `"Remind me every day at 8 AM to study Python."` | Creates daily recurring reminder; daemon advances schedule | ✅ PASSED (`test_scenario_3_recurring_reminder`) |
| **4** | `"What are my tasks today?"` | Lists pending tasks prioritized by urgency with due dates | ✅ PASSED (`test_scenario_4_tasks_query`) |
| **5** | `"Find my Django project and open it in VS Code."` | Locates project directory and launches it in Visual Studio Code | ✅ PASSED (`test_scenario_5_find_project_open_vscode`) |
| **6** | `"Take a screenshot."` | Captures primary display using Pillow into timestamped file | ✅ PASSED (`test_scenario_6_take_screenshot`) |
| **7** | `"Play relaxing music."` | Routes directly to Spotify using remembered user preference | ✅ PASSED (`test_scenario_7_play_relaxing_music`) |
| **8** | `"What were we discussing earlier?"` | Recalls prior topics discussed within the current conversation session | ✅ PASSED (`test_scenario_8_conversational_recall_earlier`) |
| **9** | `"Find my Python project and open its GitHub repository."` | Inspects `.git/config` for origin URL and opens repository in browser | ✅ PASSED (`test_scenario_9_find_project_and_open_github`) |
| **10**| `"Explain what you are doing before executing this multi-step task."` | Outlines decomposed intent and sequential verification steps before running | ✅ PASSED (`test_scenario_10_explain_plan_before_executing`) |

---

## 18. Exact Commands to Launch DADUS

1. **Launch Desktop Web UI & Background Agent:**
   ```powershell
   python app/main.py --mode web
   ```
   Open `http://127.0.0.1:8000` in Google Chrome or any modern browser.

2. **Launch Interactive Voice Mode (Wake Word `"Hey Dadus"`):**
   ```powershell
   python app/main.py --mode voice
   ```

3. **Launch Terminal CLI:**
   ```powershell
   python app/main.py --mode cli
   ```

4. **Launch Standards-Compliant MCP Server:**
   ```powershell
   python -m app.mcp.server
   ```

5. **Execute Full Automated Test Suite (70 Tests):**
   ```powershell
   python -m pytest -v
   ```

---

## License

MIT License. Engineered for DADUS.


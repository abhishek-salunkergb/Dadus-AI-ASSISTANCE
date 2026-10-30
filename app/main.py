"""Main application entry point for DADUS Personal AI Assistant."""
import sys
import os
from pathlib import Path

# Ensure project root is in sys.path so running directly via `python app/main.py` works seamlessly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import logging
import threading
import time
import uvicorn

from app.config.settings import settings
from app.database.database import init_db
from app.tools import register_default_tools
from app.agent.agent import dadus_agent
from app.voice.tts import get_tts_provider
from app.voice.stt import get_stt_provider
from app.voice.wakeword import get_wakeword_provider
from app.ui.web_ui import open_ui
from app.api.server import app as fastapi_app

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("DADUS.Main")

def start_api_server(host: str, port: int) -> None:
    """Run FastAPI uvicorn server."""
    logger.info(f"Starting DADUS API Server at http://{host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")

def run_cli_mode() -> None:
    """Interactive command-line loop for testing."""
    tts = get_tts_provider()
    print("\n" + "=" * 55)
    print("      DADUS - Personal AI Operating Assistant")
    print(f"      Wake Phrase: '{settings.WAKE_PHRASE}'")
    print("      Type 'exit' or 'quit' to quit.")
    print("=" * 55 + "\n")

    greeting = "Hello boss. DADUS is online and ready."
    print(f"Dadus: {greeting}")
    tts.speak(greeting)

    while True:
        try:
            user_input = input("\nBoss: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                farewell = "Goodbye, boss."
                print(f"Dadus: {farewell}")
                tts.speak(farewell, async_mode=False)
                break

            response = dadus_agent.process_input(user_input, session_id="cli_session")
            print(f"Dadus: {response.text}")
            if response.tool_called:
                print(f"       [Tool executed: {response.tool_called}]")
            tts.speak(response.text)

        except (KeyboardInterrupt, EOFError):
            print("\nShutting down DADUS.")
            break
        except Exception as ex:
            logger.exception(f"CLI interaction error: {ex}")
            print("Dadus: Boss, an unexpected error occurred.")

def run_voice_loop() -> None:
    """Continuous wake-word listening loop."""
    tts = get_tts_provider()
    wakeword = get_wakeword_provider()

    logger.info(f"DADUS Voice Engine running. Say '{settings.WAKE_PHRASE}' followed by your command.")
    tts.speak(f"DADUS voice monitoring active, boss. I am listening for {settings.WAKE_PHRASE}.", async_mode=False)

    def on_wake(command_text: str):
        if not command_text.strip():
            try:
                tts.stop()
            except Exception:
                pass

            # Play modern Siri-style dual activation chime
            try:
                import winsound
                winsound.Beep(880, 80)
                time.sleep(0.03)
                winsound.Beep(1320, 140)
            except Exception:
                pass

            stt = get_stt_provider()
            command_text = stt.listen_and_transcribe(timeout=6, phrase_time_limit=12) or ""

        if command_text.strip():
            logger.info(f"Processing voice command: '{command_text}'")
            resp = dadus_agent.process_input(command_text, session_id="voice_session")
            logger.info(f"DADUS response: '{resp.text}'")
            tts.speak(resp.text, async_mode=False)

    wakeword.start_listening(on_wake)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        wakeword.stop_listening()
        logger.info("Voice monitoring stopped.")

def main() -> None:
    """Parse arguments and start DADUS components."""
    parser = argparse.ArgumentParser(description="DADUS Personal AI Assistant")
    parser.add_argument("--mode", choices=["web", "voice", "cli"], default=None, help="Operating mode: web, voice, or cli")
    parser.add_argument("--cli", action="store_true", help="Start in interactive CLI mode")
    parser.add_argument("--voice", action="store_true", help="Start continuous voice wake-word monitoring")
    parser.add_argument("--window", action="store_true", help="Launch in dedicated desktop window")
    parser.add_argument("--host", default=settings.API_HOST, help="API server host")
    parser.add_argument("--port", type=int, default=settings.API_PORT, help="API server port")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser on startup")

    args = parser.parse_args()

    # 1. Initialize environment, database tables, and default tools
    settings.ensure_directories()
    init_db()
    register_default_tools()

    logger.info(f"Initialized {settings.PRODUCT_NAME} v1.0.0")

    # 2. Start API Server in background thread if CLI or voice mode requested
    if args.cli or args.mode == "cli":
        server_thread = threading.Thread(
            target=start_api_server,
            args=(args.host, args.port),
            daemon=True
        )
        server_thread.start()
        run_cli_mode()
        return

    if args.voice or args.mode == "voice":
        server_thread = threading.Thread(
            target=start_api_server,
            args=(args.host, args.port),
            daemon=True
        )
        server_thread.start()
        run_voice_loop()
        return

    # 3. Default: Launch Web / Desktop UI mode
    if not args.no_browser:
        # Schedule browser / window launch after server boots
        def _open_later():
            time.sleep(1.2)
            open_ui(use_webview=args.window)

        threading.Thread(target=_open_later, daemon=True).start()

    start_api_server(args.host, args.port)

if __name__ == "__main__":
    main()

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
    """Continuous wake-word listening loop with audio ducking and global hotkey."""
    from app.audio.ducking import audio_ducker
    from app.system.hotkey import global_hotkey

    tts = get_tts_provider()
    wakeword = get_wakeword_provider()
    stt = get_stt_provider()

    logger.info(f"DADUS Voice Engine running. Say '{settings.WAKE_PHRASE}' or press Alt+Shift+D.")
    tts.speak(f"DADUS voice monitoring active, boss. I am listening for {settings.WAKE_PHRASE}.", async_mode=False)

    _wake_lock = threading.Lock()

    def on_wake(command_text: str = ""):
        from app.api.server import sync_voice_state
        # Immediately halt active speech to enable barge-in
        try:
            tts.stop()
        except Exception:
            pass

        # Allow previous interrupted speech cycle up to 600ms to exit cleanly
        if not _wake_lock.acquire(timeout=0.6):
            logger.info("Wake event dropped: DADUS busy with non-interruptible process.")
            return

        try:
            with audio_ducker:
                sync_voice_state("listening", "Listening to boss...")
                if not command_text.strip():
                    # Play activation chime
                    try:
                        import winsound
                        winsound.Beep(880, 80)
                        time.sleep(0.03)
                        winsound.Beep(1320, 140)
                    except Exception:
                        pass

                    command_text = stt.listen_and_transcribe(timeout=6, phrase_time_limit=12) or ""

                if command_text.strip():
                    sync_voice_state("thinking", f"Processing: '{command_text}'")
                    logger.info(f"Processing voice command: '{command_text}'")
                    lower_cmd = command_text.strip().lower()
                    if lower_cmd in ["stop", "stop talking", "stop reading", "be quiet", "shut up", "cancel", "quiet", "halt"]:
                        tts.stop()
                        resp_text = "Stopped, boss."
                    else:
                        resp = dadus_agent.process_input(command_text, session_id="voice_session")
                        resp_text = resp.text

                    sync_voice_state("speaking", resp_text)
                    logger.info(f"DADUS response: '{resp_text}'")
                    tts.speak(resp_text, async_mode=False)
        finally:
            sync_voice_state("idle", "Standing by...")
            _wake_lock.release()

    # Register global hotkey (Alt + Shift + D)
    global_hotkey.start(lambda: on_wake(""))

    # Start wake word listener
    wakeword.start_listening(on_wake)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        wakeword.stop_listening()
        global_hotkey.stop()
        audio_ducker.restore()
        logger.info("Voice monitoring stopped.")

def run_tray_mode(host: str, port: int) -> None:
    """Run DADUS silently in Windows System Tray with global hotkey and background wake word."""
    from app.audio.ducking import audio_ducker
    from app.system.hotkey import global_hotkey
    from app.system.tray import dadus_tray

    tts = get_tts_provider()
    wakeword = get_wakeword_provider()
    stt = get_stt_provider()

    logger.info("Starting DADUS in Windows System Tray Daemon mode.")
    print("=" * 60)
    print("      DADUS - Personal AI Operating Assistant Daemon")
    print(f"      • Wake Phrase: '{settings.WAKE_PHRASE}'")
    print("      • Global Hotkey: Alt + Shift + D")
    print(f"      • Dashboard API: http://{host}:{port}")
    print("      • System Tray: Active in Windows Notification Area")
    print("=" * 60)

    # 1. Start API Server in background thread
    server_thread = threading.Thread(
        target=start_api_server,
        args=(host, port),
        daemon=True
    )
    server_thread.start()

    _wake_lock = threading.Lock()

    def on_wake(command_text: str = ""):
        from app.api.server import sync_voice_state
        # Immediately halt active speech to enable barge-in
        try:
            tts.stop()
        except Exception:
            pass

        # Allow previous interrupted speech cycle up to 600ms to exit cleanly
        if not _wake_lock.acquire(timeout=0.6):
            logger.info("Wake event dropped: DADUS busy with non-interruptible process.")
            return

        try:
            with audio_ducker:
                sync_voice_state("listening", "Listening to boss...")
                if not command_text.strip():
                    # Play activation chime
                    try:
                        import winsound
                        winsound.Beep(880, 80)
                        time.sleep(0.03)
                        winsound.Beep(1320, 140)
                    except Exception:
                        pass

                    command_text = stt.listen_and_transcribe(timeout=6, phrase_time_limit=12) or ""

                if command_text.strip():
                    sync_voice_state("thinking", f"Processing: '{command_text}'")
                    logger.info(f"Processing voice command: '{command_text}'")
                    lower_cmd = command_text.strip().lower()
                    if lower_cmd in ["stop", "stop talking", "stop reading", "be quiet", "shut up", "cancel", "quiet", "halt"]:
                        tts.stop()
                        resp_text = "Stopped, boss."
                    else:
                        resp = dadus_agent.process_input(command_text, session_id="tray_voice_session")
                        resp_text = resp.text

                    sync_voice_state("speaking", resp_text)
                    logger.info(f"DADUS response: '{resp_text}'")
                    tts.speak(resp_text, async_mode=False)
        finally:
            sync_voice_state("idle", "Standing by...")
            _wake_lock.release()

    # 2. Register global hotkey (Alt + Shift + D)
    global_hotkey.start(lambda: on_wake(""))

    # 3. Start background wakeword listener
    wakeword.start_listening(on_wake)

    # 4. Start System Tray icon
    shutdown_event = threading.Event()

    def on_tray_exit():
        logger.info("Shutting down from tray menu...")
        shutdown_event.set()

    dadus_tray.start(on_exit=on_tray_exit)

    # Voice confirmation of startup
    try:
        tts.speak("DADUS background daemon active, boss. Press Alt Shift D or say Hey Dadus anytime.", async_mode=False)
    except Exception:
        pass

    try:
        while not shutdown_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        logger.info("Stopping all background services...")
        wakeword.stop_listening()
        global_hotkey.stop()
        dadus_tray.stop()
        audio_ducker.restore()
        logger.info("DADUS shutdown complete.")

def main() -> None:
    """Parse arguments and start DADUS components."""
    parser = argparse.ArgumentParser(description="DADUS Personal AI Assistant")
    parser.add_argument("--mode", choices=["web", "voice", "cli", "tray"], default=None, help="Operating mode: web, voice, cli, or tray")
    parser.add_argument("--cli", action="store_true", help="Start in interactive CLI mode")
    parser.add_argument("--voice", action="store_true", help="Start continuous voice wake-word monitoring")
    parser.add_argument("--tray", action="store_true", help="Start silently in Windows System Tray with global hotkey and background wake listener")
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

    # 2. System Tray Daemon mode
    if args.tray or args.mode == "tray":
        run_tray_mode(args.host, args.port)
        return

    # 3. Start API Server in background thread if CLI or voice mode requested
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

    # 4. Default: Launch Web / Desktop UI mode
    import socket
    def is_port_busy(h: str, p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex((h, p)) == 0

    if is_port_busy(args.host, args.port):
        # Check if DADUS is already active and responding
        try:
            import urllib.request
            req = urllib.request.urlopen(f"http://{args.host}:{args.port}/api/status", timeout=1.0)
            if req.status == 200:
                logger.info(f"DADUS API Server is already active on http://{args.host}:{args.port}.")
                if not args.no_browser:
                    open_ui(use_webview=args.window, port=args.port)
                return
        except Exception:
            pass

        # If port is held by an unknown process, try next fallback port
        orig = args.port
        for fp in [8001, 8002, 8080]:
            if not is_port_busy(args.host, fp):
                args.port = fp
                logger.info(f"Port {orig} was occupied; dynamically bound DADUS to http://{args.host}:{args.port}")
                break

    if not args.no_browser:
        # Schedule browser / window launch after server boots
        def _open_later():
            time.sleep(1.2)
            open_ui(use_webview=args.window, port=args.port)

        threading.Thread(target=_open_later, daemon=True).start()

    start_api_server(args.host, args.port)

if __name__ == "__main__":
    main()

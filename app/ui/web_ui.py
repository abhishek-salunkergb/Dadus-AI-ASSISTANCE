"""Desktop window launcher for DADUS UI."""
import webbrowser
import logging
from app.config.settings import settings

logger = logging.getLogger("DADUS.UI")

def open_ui(use_webview: bool = False) -> None:
    """Launch the DADUS interface in a dedicated window or browser."""
    url = f"http://{settings.API_HOST}:{settings.API_PORT}/"
    if use_webview:
        try:
            import webview
            logger.info("Opening DADUS in dedicated desktop window...")
            webview.create_window(
                f"{settings.PRODUCT_NAME} - Operating Assistant",
                url,
                width=1100,
                height=780,
                min_size=(900, 600)
            )
            webview.start()
            return
        except Exception as ex:
            logger.warning(f"Could not open pywebview window, falling back to browser: {ex}")

    logger.info(f"Opening DADUS in default web browser: {url}")
    webbrowser.open(url)

"""Windows native desktop notification provider for DADUS.
Delivers non-blocking toast notifications directly to the Windows Action Center/Notification Area.
"""
import subprocess
import threading
import logging
from typing import Optional

logger = logging.getLogger("DADUS.Notifications")

def show_desktop_notification(
    title: str,
    message: str,
    app_id: str = "DADUS AI Assistant",
    async_mode: bool = True
) -> bool:
    """
    Displays a native Windows toast notification non-blockingly.
    Compatible with Windows 10/11. Gracefully handles errors in headless or test environments.
    """
    def _dispatch() -> None:
        try:
            # Escape single quotes and backticks for PowerShell script
            safe_title = title.replace("`", "``").replace("'", "''").replace('"', '`"')
            safe_msg = message.replace("`", "``").replace("'", "''").replace('"', '`"')

            ps_script = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
                "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                "$textNodes = $template.GetElementsByTagName('text'); "
                f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null; "
                f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_msg}')) | Out-Null; "
                f"$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}'); "
                "$notification = [Windows.UI.Notifications.ToastNotification]::new($template); "
                "$notifier.Show($notification);"
            )

            # 0x08000000 = CREATE_NO_WINDOW (prevents any temporary console flash)
            CREATE_NO_WINDOW = 0x08000000
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_script],
                creationflags=CREATE_NO_WINDOW,
                timeout=5,
                capture_output=True
            )
            logger.debug(f"Desktop toast sent: '{title}' - '{message}'")
        except Exception as ex:
            logger.debug(f"Desktop notification failed: {ex}")

    if async_mode:
        threading.Thread(target=_dispatch, daemon=True).start()
    else:
        _dispatch()

    return True

notify_user = show_desktop_notification


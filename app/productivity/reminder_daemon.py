"""Background reminder and notification daemon for DADUS.
Monitors due reminders, handles application restarts/missed reminders, and advances recurring schedules.
"""
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from app.database.database import get_db_context
from app.database.models import Reminder
from app.voice.tts import get_tts_provider

logger = logging.getLogger("DADUS.ReminderDaemon")

class ReminderDaemon:
    """Background worker daemon for reminders."""

    def __init__(self, check_interval_seconds: int = 10):
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Background Reminder Daemon started.")

    def stop(self) -> None:
        """Stop daemon thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Background Reminder Daemon stopped.")

    def _run_loop(self) -> None:
        # Check missed reminders once on startup
        self._check_missed_reminders()

        while self._running:
            try:
                self._check_due_reminders()
            except Exception as ex:
                logger.error(f"Error in reminder loop: {ex}")
            time.sleep(self.check_interval)

    def _check_missed_reminders(self) -> None:
        """Find reminders that matured while the system/app was shut down."""
        now = datetime.now()
        with get_db_context() as db:
            missed = db.query(Reminder).filter(
                Reminder.status == "pending",
                Reminder.target_time < now - timedelta(minutes=5)
            ).all()

            for r in missed:
                diff_mins = int((now - r.target_time).total_seconds() // 60)
                notice = f"Boss, you had a missed reminder: '{r.title}', scheduled {diff_mins} minutes ago."
                logger.warning(f"Missed reminder detected: {r.title}")
                get_tts_provider().speak(notice, async_mode=True)

                if r.recurrence == "daily":
                    # Advance to next day
                    r.target_time += timedelta(days=1)
                    r.last_notified_at = datetime.utcnow()
                elif r.recurrence == "weekly":
                    r.target_time += timedelta(weeks=1)
                    r.last_notified_at = datetime.utcnow()
                else:
                    r.status = "completed"
                    r.last_notified_at = datetime.utcnow()
            db.flush()

    def _check_due_reminders(self) -> None:
        """Find reminders that are due right now."""
        now = datetime.now()
        with get_db_context() as db:
            due = db.query(Reminder).filter(
                Reminder.status == "pending",
                Reminder.target_time <= now
            ).all()

            for r in due:
                alert = f"Boss, reminder: {r.title}."
                logger.info(f"Firing reminder alert: '{r.title}'")
                get_tts_provider().speak(alert, async_mode=True)

                if r.recurrence == "daily":
                    r.target_time += timedelta(days=1)
                    r.last_notified_at = datetime.utcnow()
                elif r.recurrence == "weekly":
                    r.target_time += timedelta(weeks=1)
                    r.last_notified_at = datetime.utcnow()
                else:
                    r.status = "completed"
                    r.last_notified_at = datetime.utcnow()
            db.flush()

reminder_daemon = ReminderDaemon()

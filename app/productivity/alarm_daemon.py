"""Background alarm execution and notification daemon for DADUS.
Monitors due alarms with 1-second precision, executes audible tones, desktop notifications,
handles system reboot/sleep recovery for missed alarms, and manages recurring schedules.
"""
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Callable

from app.database.database import get_db_context
from app.database.models import Alarm
from app.voice.tts import get_tts_provider
from app.system import notifications

logger = logging.getLogger("DADUS.AlarmDaemon")


class AlarmDaemon:
    """Independent background worker daemon for scheduling and firing alarms."""

    def __init__(self, check_interval_seconds: float = 1.0):
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._listeners: List[Callable[[dict], None]] = []

    def add_listener(self, listener: Callable[[dict], None]) -> None:
        """Register a callback for fired alarms (e.g., UI WebSockets)."""
        self._listeners.append(listener)

    def start(self) -> None:
        """Start the background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="DADUS-AlarmDaemon")
        self._thread.start()
        logger.info("Background Alarm Daemon started.")

    def stop(self) -> None:
        """Stop the background daemon thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Background Alarm Daemon stopped.")

    def _run_loop(self) -> None:
        # Check missed alarms once on startup / reboot recovery
        try:
            self._check_missed_alarms()
        except Exception as ex:
            logger.error(f"Error checking missed alarms during startup: {ex}")

        while self._running:
            try:
                self._check_due_alarms()
            except Exception as ex:
                logger.error(f"Error in alarm loop: {ex}")
            time.sleep(self.check_interval)

    def _check_missed_alarms(self) -> None:
        """Identifies alarms that matured while the system was offline, sleeping, or restarting."""
        now = datetime.now()
        with get_db_context() as db:
            # Alarms older than 2 minutes in the past that are still 'scheduled'
            missed = db.query(Alarm).filter(
                Alarm.status == "scheduled",
                Alarm.target_time < now - timedelta(minutes=2)
            ).all()

            for a in missed:
                diff_mins = int((now - a.target_time).total_seconds() // 60)
                time_str = a.target_time.strftime("%I:%M %p").lstrip("0")
                logger.warning(f"Missed alarm detected: #{a.id} '{a.label}' scheduled for {time_str} ({diff_mins}m ago)")

                # Notify user of missed alarm
                notice = f"Boss, you had a missed alarm: '{a.label}', scheduled {diff_mins} minutes ago at {time_str}."
                try:
                    get_tts_provider().speak(notice, async_mode=True)
                except Exception:
                    pass
                notifications.show_desktop_notification(
                    title="Missed Alarm",
                    message=f"{a.label} ({time_str}, {diff_mins}m ago)"
                )

                if a.recurrence == "daily":
                    a.target_time += timedelta(days=1)
                elif a.recurrence == "weekdays":
                    # Advance to next weekday
                    next_day = a.target_time + timedelta(days=1)
                    while next_day.weekday() >= 5:  # 5=Sat, 6=Sun
                        next_day += timedelta(days=1)
                    a.target_time = next_day
                elif a.recurrence == "weekends":
                    next_day = a.target_time + timedelta(days=1)
                    while next_day.weekday() < 5:
                        next_day += timedelta(days=1)
                    a.target_time = next_day
                else:
                    a.status = "missed"
            db.flush()

    def _check_due_alarms(self) -> None:
        """Finds and executes alarms that are due right now."""
        now = datetime.now()
        with get_db_context() as db:
            due_alarms = db.query(Alarm).filter(
                Alarm.status == "scheduled",
                Alarm.target_time <= now
            ).all()

            for a in due_alarms:
                # 1. Update status to prevent repeated execution
                a.status = "triggered"
                a.triggered_at = datetime.utcnow()
                alarm_data = a.to_dict()

                time_str = a.target_time.strftime("%I:%M %p").lstrip("0")
                label = a.label or "Alarm"
                logger.info(f"Triggering alarm #{a.id}: '{label}' at {time_str}")

                # 2. Fire audible sound tone and desktop notification
                self._play_alarm_sound()
                notifications.show_desktop_notification(
                    title=f"DADUS Alarm: {label}",
                    message=f"It is {time_str}. Time for: {label}."
                )

                # 3. Spoken voice announcement
                spoken_alert = f"Boss, your {time_str} alarm for {label} is ringing!"
                try:
                    get_tts_provider().speak(spoken_alert, async_mode=True)
                except Exception as ex:
                    logger.debug(f"Alarm voice speak error: {ex}")

                # 4. Handle recurrence by scheduling next occurrence
                if a.recurrence == "daily":
                    next_alarm = Alarm(
                        label=a.label,
                        target_time=a.target_time + timedelta(days=1),
                        status="scheduled",
                        recurrence="daily",
                        sound=a.sound,
                        created_at=datetime.utcnow()
                    )
                    db.add(next_alarm)
                elif a.recurrence == "weekdays":
                    next_day = a.target_time + timedelta(days=1)
                    while next_day.weekday() >= 5:
                        next_day += timedelta(days=1)
                    next_alarm = Alarm(
                        label=a.label,
                        target_time=next_day,
                        status="scheduled",
                        recurrence="weekdays",
                        sound=a.sound,
                        created_at=datetime.utcnow()
                    )
                    db.add(next_alarm)

                # 5. Notify registered event listeners
                for listener in self._listeners:
                    try:
                        listener(alarm_data)
                    except Exception:
                        pass

            db.flush()

    def _play_alarm_sound(self) -> None:
        """Plays an audible alarm sound via Windows system sound or chime."""
        def _sound_thread():
            try:
                import winsound
                # Play audible 3-beep alarm chime
                for freq in [1000, 1200, 1500]:
                    winsound.Beep(freq, 250)
                    time.sleep(0.05)
            except Exception as ex:
                logger.debug(f"Could not play native alarm beep: {ex}")

        threading.Thread(target=_sound_thread, daemon=True).start()


alarm_daemon = AlarmDaemon()


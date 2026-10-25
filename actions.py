"""
actions.py - everything the program DOES to your computer.

So far: sounds (Step 2), the Windows master volume (Step 4), the media
play/pause key and the countdown timer (Step 5), mouse scrolling (Step 6) and
zoom (Step 7) and screenshots (Step 8).
"""

import datetime
import os
import threading
import time
import winsound

import pyautogui
import pywintypes
import win32api
import win32con
import win32gui
import win32process
from PIL import ImageGrab
from pycaw.pycaw import AudioUtilities
from win32com.shell import shell, shellcon
from winotify import Notification

import config

pyautogui.FAILSAFE = config.PYAUTOGUI_FAILSAFE
pyautogui.PAUSE = config.PYAUTOGUI_PAUSE


def play_sound(path):
    """
    Play a .wav file without freezing the program (SND_ASYNC = play in the
    background). If the file is missing, play ONE short fallback beep instead.
    """
    if os.path.isfile(path):
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        play_beep([config.FALLBACK_BEEP])


def play_sound_for(path, seconds):
    """
    Play a .wav file but stop it `seconds` after the request (for long sounds).
    Does not block: a small background thread plays it, waits, then stops it.
    The thread stays alive the whole time because Windows can cut off an async
    sound if the thread that started it ends first.
    """
    if not os.path.isfile(path):
        play_beep([config.FALLBACK_BEEP])
        return

    def _play():
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        time.sleep(seconds)
        # SND_PURGE with no file = "stop whatever is playing now".
        winsound.PlaySound(None, winsound.SND_PURGE)

    threading.Thread(target=_play, daemon=True).start()


# winsound.Beep() freezes the program until the tone ends. To keep the camera
# loop smooth we play beeps in a small background thread. The lock makes sure
# two beep patterns never play over each other.
_beep_lock = threading.Lock()


def play_beep(pattern):
    """Play a list of (frequency_hz, duration_ms) tones without blocking."""

    def _play():
        with _beep_lock:
            for frequency, duration in pattern:
                winsound.Beep(frequency, duration)

    threading.Thread(target=_play, daemon=True).start()


class VolumeController:
    """
    Reads and changes the Windows master volume (the one on your speaker icon).

    pycaw is a Python wrapper around the Windows audio system. Volume is a
    number from 0.0 (silent) to 1.0 (full); we show it as a percentage.
    """

    def __init__(self):
        self._endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        self._level = self._endpoint.GetMasterVolumeLevelScalar()
        self._last_read = time.monotonic()

    @property
    def percent(self):
        """Current volume as a whole percentage (0-100)."""
        return round(self.level * 100)

    @property
    def level(self):
        """Volume 0.0-1.0. Re-read from Windows every VOLUME_POLL_SECONDS, so
        changes made with the keyboard or the taskbar also show up here."""
        now = time.monotonic()
        if now - self._last_read >= config.VOLUME_POLL_SECONDS:
            self._level = self._endpoint.GetMasterVolumeLevelScalar()
            self._last_read = now
        return self._level

    def change(self, steps):
        """Move the volume by `steps` x VOLUME_STEP_PERCENT (negative = quieter)."""
        # Start from the real current value, not the cached one.
        current = self._endpoint.GetMasterVolumeLevelScalar()
        new = current + steps * config.VOLUME_STEP_PERCENT / 100
        new = max(0.0, min(1.0, new))      # keep it between 0% and 100%
        self._endpoint.SetMasterVolumeLevelScalar(new, None)
        self._level = new
        self._last_read = time.monotonic()


def send_play_pause():
    """Press the media play/pause key (works for Spotify, YouTube, VLC...)."""
    pyautogui.press(config.KEY_PLAY_PAUSE)


def scroll(units):
    """
    Scroll the window under the mouse pointer by `units` wheel units (120 = one
    notch; smaller amounts give smooth scrolling in browsers and most apps).
    `units` > 0 means the finger moved UP, < 0 DOWN. With SCROLL_INVERT = False
    (touchscreen style) a finger moving UP makes the view travel DOWN the page.
    """
    amount = units if config.SCROLL_INVERT else -units
    # pyautogui.scroll: positive = wheel forward = view moves UP the page.
    pyautogui.scroll(amount)


def zoom(steps):
    """
    Zoom with Ctrl + mouse wheel (works in browsers, photo viewers, Office...).
    `steps` > 0 = zoom in (wheel forward), < 0 = zoom out.
    """
    # hold() presses Ctrl and ALWAYS lets go again, even if something fails,
    # so Ctrl can never get stuck down.
    with pyautogui.hold("ctrl"):
        pyautogui.scroll(steps * config.ZOOM_NOTCHES_PER_STEP * config.WHEEL_DELTA)


def focus_window_under_pointer():
    """
    Give keyboard focus to the window under the mouse pointer.

    Mouse-wheel actions (scroll, zoom) go to the window under the pointer, but
    KEY presses go to the window with keyboard focus - which is often our own
    preview window. So before sending a shortcut we bring the hovered window
    to the front. Returns True if that window now has focus.
    """
    hovered = win32gui.WindowFromPoint(win32gui.GetCursorPos())
    if not hovered:
        return False
    target = win32gui.GetAncestor(hovered, win32con.GA_ROOT)   # the whole window, not a button inside it
    foreground = win32gui.GetForegroundWindow()
    if target == foreground:
        return True
    try:
        win32gui.SetForegroundWindow(target)
    except pywintypes.error:
        # Windows only lets the active program change focus. Temporarily
        # sharing the active window's input queue is the standard workaround.
        active_thread = win32process.GetWindowThreadProcessId(foreground)[0]
        my_thread = win32api.GetCurrentThreadId()
        win32process.AttachThreadInput(my_thread, active_thread, True)
        try:
            win32gui.SetForegroundWindow(target)
        except pywintypes.error:
            pass
        finally:
            win32process.AttachThreadInput(my_thread, active_thread, False)
    time.sleep(config.FOCUS_SETTLE_SECONDS)     # give Windows a moment to switch
    return win32gui.GetForegroundWindow() == target


def screenshots_folder():
    """
    <Pictures>/Screenshots, created if missing. The Pictures folder comes from
    the Windows known-folder API because it can be moved (for example into OneDrive).
    """
    pictures = shell.SHGetKnownFolderPath(shellcon.FOLDERID_Pictures, 0, 0)
    folder = os.path.join(pictures, config.SCREENSHOT_FOLDER_NAME)
    os.makedirs(folder, exist_ok=True)
    return folder


def take_screenshot():
    """
    Capture the whole primary screen and save it as a PNG named
    gesture_YYYY-MM-DD_HH-MM-SS.png. The picture is taken right away, but
    writing the PNG file takes a moment, so that happens in a background
    thread. Returns the full path of the file that is being saved.
    """
    folder = screenshots_folder()
    path = os.path.join(folder, datetime.datetime.now().strftime(config.SCREENSHOT_FILENAME_FORMAT))
    image = ImageGrab.grab()
    threading.Thread(target=image.save, args=(path, "PNG"), daemon=True).start()
    return path


def reset_zoom():
    """Reset zoom to 100% with Ctrl+0 (the usual "actual size" shortcut)."""
    focus_window_under_pointer()      # the keys must reach the window you are pointing at
    pyautogui.hotkey(*config.RESET_ZOOM_KEYS)


class CountdownTimer:
    """
    A countdown that runs in its own background thread, so the camera loop is
    never blocked. When it reaches zero it shows a Windows notification and
    plays the timer-finished beep pattern.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._end_time = None            # time.monotonic() value when it finishes
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def running(self):
        with self._lock:
            return self._end_time is not None

    @property
    def remaining_seconds(self):
        """Seconds left (0 if not running)."""
        with self._lock:
            if self._end_time is None:
                return 0
            return max(0.0, self._end_time - time.monotonic())

    def start(self):
        """Start the countdown. Returns False (and does nothing) if one is already running."""
        with self._lock:
            if self._end_time is not None:
                return False
            self._end_time = time.monotonic() + config.TIMER_MINUTES * 60
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return True

    def _run(self):
        # wait() sleeps until the time is up, but wakes up at once if stop() is called.
        stopped_early = self._stop_event.wait(timeout=self.remaining_seconds)
        with self._lock:
            self._end_time = None
        if stopped_early:
            return
        play_sound_for(config.SOUND_TIMER_DONE, config.TIMER_DONE_SOUND_SECONDS)
        try:
            Notification(app_id=config.TOAST_APP_ID, title=config.TIMER_DONE_TITLE,
                         msg=config.TIMER_DONE_MESSAGE).show()
        except Exception as error:     # a failed notification must never crash the thread
            print(f"Could not show the notification: {error}")

    def stop(self):
        """Cancel the timer and end its thread (used when the program quits)."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)

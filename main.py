"""
main.py - starts the program and runs the camera loop.

So far:
  * a startup dialog to choose "Show preview" or "Minimize"
  * Ctrl+Alt+G toggles control ON/OFF from any window (camera off while OFF)
  * Ctrl+Alt+Q or Esc quits cleanly
  * the ON/OFF state shown on the preview
  * a dialog if the camera can't be opened or is covered
  * Step 3: the detected hand shape shown on each hand, plus a debug line
    per hand (press D to show/hide).
  * Step 4: LEFT hand POINTING, moved up/down, changes the Windows volume.
  * Step 5: LEFT hand FIST held 2 s = play/pause, OPEN PALM held 2 s = 5-minute timer.
  * Step 6: RIGHT hand POINTING (finger up or sideways), moved up/down, scrolls.
  * Step 7: RIGHT hand NEAR-PINCH (or ZOOM SPREAD), then spreading / closing
    thumb and index = zoom in / out.
    RIGHT hand OPEN PALM held 2 s = reset zoom to 100% (Ctrl+0).
  * Step 8: RIGHT hand FLAT HAND held 2 s = screenshot to Pictures/Screenshots.
  * Step 9: only ONE gesture at a time (GestureLock); everything else is ignored
    until that gesture is released.
"""

import os
import threading
import time
import tkinter as tk

import cv2
import keyboard
import win32api
import win32con
import win32gui
from mediapipe.tasks.python import vision

import actions
import config
from gestures import (FIST, FLAT_HAND, NEAR_PINCH, OPEN_PALM, POINTING, POINTING_SIDE,
                      ZOOM_SPREAD,
                      ContinuousGesture, GestureLock, HandAnalyzer, HandTracker,
                      HoldGesture, JoystickScroll, ScrollGesture, SwipeScroll,
                      ZoomGesture)

# Pairs of landmark numbers that should be joined by a line (the "skeleton").
HAND_CONNECTIONS = [(c.start, c.end)
                    for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
WRIST = 0  # landmark number of the wrist


class ControlState:
    """
    Remembers whether gesture control is ON or OFF, and whether we should quit.

    The hotkeys run in a different thread from the camera loop, so changes are
    protected by a lock to avoid the two threads stepping on each other.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.enabled = False            # control starts OFF
        self.quit_requested = False

    def set_enabled(self, value):
        """Turn control ON/OFF and play the matching sound. Does nothing if unchanged."""
        with self._lock:
            if self.enabled == value:
                return
            self.enabled = value
        actions.play_sound(config.SOUND_ON if value else config.SOUND_OFF)
        if not value:
            self.stop_all_actions()

    def toggle(self):
        self.set_enabled(not self.enabled)

    def request_quit(self):
        with self._lock:
            self.quit_requested = True

    def stop_all_actions(self):
        """Called when control turns OFF. Later steps will cancel volume/scroll/zoom here."""
        pass


def ask_preview_mode(tk_root):
    """Show a small dialog and return PREVIEW_MODE_SHOW / PREVIEW_MODE_MINIMIZE (or None if closed)."""
    chosen = {"mode": None}
    dialog = tk.Toplevel(tk_root)
    dialog.title(config.DIALOG_TITLE)
    dialog.resizable(False, False)
    pad = config.DIALOG_PADDING

    tk.Label(dialog, text="How should the camera preview behave?").pack(padx=pad, pady=pad)
    mode_var = tk.StringVar(master=dialog, value=config.PREVIEW_MODE_SHOW)
    tk.Radiobutton(dialog, text="Mode 1: Show preview", variable=mode_var,
                   value=config.PREVIEW_MODE_SHOW).pack(anchor="w", padx=pad)
    tk.Radiobutton(dialog, text="Mode 2: Minimize (click the taskbar icon to look)",
                   variable=mode_var, value=config.PREVIEW_MODE_MINIMIZE).pack(anchor="w", padx=pad)

    def on_start():
        chosen["mode"] = mode_var.get()
        dialog.destroy()

    tk.Button(dialog, text="Start", command=on_start).pack(pady=pad)
    tk_root.wait_window(dialog)   # waits here until the dialog is closed
    return chosen["mode"]


def show_camera_error(tk_root, message, state):
    """
    Show the camera-problem dialog and wait for the user's choice.

    Returns "retry", "off" (user pressed Turn off or closed the dialog) or
    "cancel" (the dialog closed itself because control was switched off or we
    are quitting, so there is nothing more to do).

    We build the dialog from plain tkinter widgets instead of messagebox,
    because messagebox plays its own Windows sound and we want ONLY ding.wav.
    """
    result = {"choice": "off"}
    dialog = tk.Toplevel(tk_root)
    dialog.title(config.CAMERA_DIALOG_TITLE)
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)   # show above the window you are working in
    pad = config.DIALOG_PADDING

    tk.Label(dialog, text=message, wraplength=360, justify="left").pack(padx=pad, pady=pad)
    buttons = tk.Frame(dialog)
    buttons.pack(pady=pad)

    def choose(choice):
        if dialog.winfo_exists():
            result["choice"] = choice
            dialog.destroy()

    tk.Button(buttons, text="Retry", command=lambda: choose("retry")).pack(side="left", padx=pad)
    tk.Button(buttons, text="Turn off", command=lambda: choose("off")).pack(side="left", padx=pad)

    # The hotkeys still work while the dialog is open, so check regularly
    # whether we should close it (control switched OFF by hotkey, or quitting).
    def check_state():
        if not dialog.winfo_exists():
            return
        if state.quit_requested or not state.enabled:
            choose("cancel")
        else:
            dialog.after(config.CAMERA_DIALOG_POLL_MS, check_state)

    dialog.after(config.CAMERA_DIALOG_POLL_MS, check_state)
    actions.play_sound(config.SOUND_DIALOG)
    tk_root.wait_window(dialog)   # waits here until the dialog is closed
    return result["choice"]


def open_camera():
    """Open the webcam. Returns the capture object, or None if it cannot be used."""
    # CAP_DSHOW (DirectShow) usually opens a Windows webcam much faster.
    camera = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not camera.isOpened():
        camera.release()
        return None
    return camera


def camera_looks_blocked(frame):
    """
    True if the lens seems covered. Two cases:
      1. DARK: average brightness is very low (tape, closed shutter, dark hand).
      2. FLAT + RED: a finger lets light through, so the image is not dark, but
         it has almost no detail and the red channel dominates.
    """
    small = cv2.resize(frame, config.BLOCK_CHECK_SIZE)    # tiny copy = fast
    if small.mean() < config.DARK_BRIGHTNESS_THRESHOLD:
        return True
    blue, green, red = (float(small[:, :, i].mean()) for i in range(3))   # OpenCV order is BGR
    detail = float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).std())   # variation across the image
    red_ratio = red / max((blue + green) / 2, 1.0)                  # max() avoids dividing by 0
    return detail < config.FLAT_DETAIL_THRESHOLD and red_ratio > config.RED_RATIO_THRESHOLD


def create_preview_window(saved_rect):
    """
    Create the preview window (resizable and movable) at its starting size.
    `saved_rect` = (left, top, width, height) where the user last left it, or
    None the first time (then it starts in the bottom right corner).
    """
    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    if saved_rect is not None:
        left, top, width, height = saved_rect
    else:
        width, height = config.PREVIEW_WIDTH, config.PREVIEW_HEIGHT
        left = win32api.GetSystemMetrics(win32con.SM_CXSCREEN) - width - config.PREVIEW_MARGIN
        top = (win32api.GetSystemMetrics(win32con.SM_CYSCREEN) - height
               - config.PREVIEW_MARGIN - config.PREVIEW_TASKBAR_ALLOWANCE)
    cv2.resizeWindow(config.WINDOW_NAME, width, height)
    cv2.moveWindow(config.WINDOW_NAME, left, top)


def read_preview_rect(hwnd):
    """The window's current (left, top, width, height), or None if it is minimized/closed."""
    if not hwnd or not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
        return None
    left, top, _, _ = win32gui.GetWindowRect(hwnd)
    _, _, width, height = cv2.getWindowImageRect(config.WINDOW_NAME)
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def screenshot_without_preview(hwnd):
    """Take a screenshot, hiding the preview window first so it is not in the picture."""
    hide = (config.SCREENSHOT_HIDE_PREVIEW and hwnd and win32gui.IsWindow(hwnd)
            and win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd))
    if hide:
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        time.sleep(config.SCREENSHOT_HIDE_DELAY_SECONDS)
    try:
        return actions.take_screenshot()
    finally:
        if hide:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)   # back, without grabbing focus


def draw_text(frame, text, x, y, color, scale=None):
    """Draw text with a dark box behind it so it is readable on any background."""
    scale = scale or config.FONT_SCALE
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(text, font, scale, config.FONT_THICKNESS)
    pad = config.TEXT_PADDING_PX
    cv2.rectangle(frame, (x - pad, y - h - pad), (x + w + pad, y + baseline + pad),
                  config.COLOR_TEXT_BG, cv2.FILLED)
    cv2.putText(frame, text, (x, y), font, scale, color,
                config.FONT_THICKNESS, cv2.LINE_AA)


def draw_hand(frame, hand):
    """Draw one hand's skeleton, its landmark points, its label and its shape."""
    height, width = frame.shape[:2]
    if not hand["in_frame"]:
        color = config.COLOR_HAND_PARTIAL       # grey = ignored
    elif hand["label"] == "Left":
        color = config.COLOR_LEFT_HAND
    else:
        color = config.COLOR_RIGHT_HAND

    # Convert normalized (0..1) coordinates to pixel coordinates.
    points = [(int(x * width), int(y * height)) for x, y, _ in hand["landmarks"]]

    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, points[start], points[end], color, config.LINE_THICKNESS)
    for point in points:
        cv2.circle(frame, point, config.LANDMARK_RADIUS, config.COLOR_LANDMARK_POINT, cv2.FILLED)

    wrist_x, wrist_y = points[WRIST]
    if not hand["in_frame"]:
        label = f"{hand['label']}: partly outside frame"
    else:
        label = f"{hand['label']}: {hand['shape'] or '-'}"
        if hand.get("ignored"):
            label += " (ignored)"      # blocked by the one-gesture-at-a-time lock
    label_y = wrist_y + config.LABEL_OFFSET_PX
    # Keep the label inside the window even when the wrist is near the bottom.
    label_y = min(label_y, height - config.HINT_TEXT_Y_OFFSET - config.LABEL_OFFSET_PX)
    shape_color = config.COLOR_SHAPE_TEXT if hand.get("shape") else color
    draw_text(frame, label, wrist_x, label_y, shape_color)


def debug_line(hand):
    """
    One line of numbers for a hand, e.g.
      R I+ M- R- P- | thumb fold 0.42 | pinch 0.85 | spread 35 | hand 92 idx 88 | front | raw POINTING
    + = extended, - = curled. Distances are in hand sizes, angles (spread, hand, idx) in degrees.
    """
    side = hand["label"][0]   # "L" or "R"
    f = hand["features"]
    if f is None:
        return f"{side}: partly outside frame - ignored"
    fingers = " ".join(name[0].upper() + ("+" if f["extended"][name] else "-")
                       for name in ("index", "middle", "ring", "pinky"))
    thumb = "fold" if f["thumb_folded"] else "out"
    palm = "front" if f["palm_front"] else "back"
    return (f"{side} {fingers} | thumb {thumb} {f['thumb_dist']:.2f} | "
            f"pinch {f['pinch_dist']:.2f} | spread {f['spread']:.0f} | "
            f"hand {f['hand_angle']:.0f} idx {f['index_angle']:.0f} | {palm} | "
            f"raw {hand['raw_shape'] or '-'}")


def draw_debug(frame, hands):
    """Draw one debug line per hand, under the ON/OFF status."""
    for i, hand in enumerate(sorted(hands, key=lambda h: h["label"])):
        y = config.DEBUG_TEXT_Y + config.VOLUME_TEXT_Y_OFFSET + i * config.DEBUG_LINE_SPACING
        draw_text(frame, debug_line(hand), config.STATUS_TEXT_X, y,
                  config.COLOR_TEXT, config.DEBUG_FONT_SCALE)


def draw_hold_bar(frame, label, progress, waiting):
    """Progress bar (bottom centre) that fills while a one-time gesture is held."""
    height, width = frame.shape[:2]
    x = (width - config.HOLD_BAR_WIDTH) // 2
    y = height - config.HOLD_BAR_BOTTOM_OFFSET
    cv2.rectangle(frame, (x, y), (x + config.HOLD_BAR_WIDTH, y + config.HOLD_BAR_HEIGHT),
                  config.COLOR_HOLD_BAR_BG, cv2.FILLED)
    fill = int(config.HOLD_BAR_WIDTH * min(progress, 1.0))
    color = config.COLOR_HOLD_BAR_WAIT if waiting else config.COLOR_HOLD_BAR
    cv2.rectangle(frame, (x, y), (x + fill, y + config.HOLD_BAR_HEIGHT), color, cv2.FILLED)
    text = f"{label} (release hand / wait)" if waiting else label
    draw_text(frame, text, x, y - config.TEXT_PADDING_PX * 2, config.COLOR_TEXT,
              config.HINT_FONT_SCALE)


def draw_timer(frame, seconds_left):
    """Countdown MM:SS in the top right corner."""
    minutes, seconds = divmod(int(seconds_left + 0.999), 60)    # round UP so 0:00 only shows at the end
    text = f"Timer {minutes:02d}:{seconds:02d}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, _), _ = cv2.getTextSize(text, font, config.FONT_SCALE, config.FONT_THICKNESS)
    x = frame.shape[1] - w - config.TIMER_TEXT_MARGIN_RIGHT
    draw_text(frame, text, x, config.STATUS_TEXT_Y, config.COLOR_TIMER_TEXT)


def draw_scroll_centre(frame, centre_y):
    """Joystick scroll: show the 'stop' band around the starting height."""
    height, width = frame.shape[:2]
    for edge in (centre_y - config.SCROLL_JOYSTICK_DEADZONE, centre_y + config.SCROLL_JOYSTICK_DEADZONE):
        y = int(edge * height)
        cv2.line(frame, (0, y), (width, y), config.COLOR_SCROLL_CENTRE, 1)
    y = int(centre_y * height)
    draw_text(frame, "stop", config.STATUS_TEXT_X, y, config.COLOR_SCROLL_CENTRE,
              config.HINT_FONT_SCALE)


def draw_activity(frame, text, color, row):
    """Small status word in the top right corner, under the timer (row 1, 2, ...)."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, _), _ = cv2.getTextSize(text, font, config.FONT_SCALE, config.FONT_THICKNESS)
    x = frame.shape[1] - w - config.TIMER_TEXT_MARGIN_RIGHT
    draw_text(frame, text, x, config.STATUS_TEXT_Y + row * config.ACTIVITY_TEXT_Y_OFFSET, color)


def draw_notice(frame, text):
    """A short message near the bottom, e.g. 'Timer already running'."""
    draw_text(frame, text, config.STATUS_TEXT_X, frame.shape[0] - config.NOTICE_Y_OFFSET,
              config.COLOR_NOTICE_TEXT)


def draw_status(frame, enabled, volume_percent, adjusting_volume):
    """Draw 'Control: ON/OFF', the volume level and a hotkey reminder."""
    text = "Control: ON" if enabled else "Control: OFF"
    color = config.COLOR_STATE_ON if enabled else config.COLOR_STATE_OFF
    draw_text(frame, text, config.STATUS_TEXT_X, config.STATUS_TEXT_Y, color)

    volume_text = f"Volume: {volume_percent}%" + ("  (adjusting)" if adjusting_volume else "")
    draw_text(frame, volume_text, config.STATUS_TEXT_X,
              config.STATUS_TEXT_Y + config.VOLUME_TEXT_Y_OFFSET, config.COLOR_VOLUME_TEXT)

    hint = f"{config.TOGGLE_HOTKEY} toggle | {config.QUIT_HOTKEY} / Esc quit"
    draw_text(frame, hint, config.STATUS_TEXT_X, frame.shape[0] - config.HINT_TEXT_Y_OFFSET,
              config.COLOR_TEXT, config.HINT_FONT_SCALE)


def main():
    # ONE hidden tkinter root for the whole program, created and destroyed on
    # the main thread. (Creating a new Tk() for every dialog crashed with
    # "Tcl_AsyncDelete: async handler deleted by the wrong thread", because
    # Python could clean the old one up from a different thread.)
    tk_root = tk.Tk()
    tk_root.withdraw()

    preview_mode = ask_preview_mode(tk_root)
    if preview_mode is None:
        tk_root.destroy()
        return  # the dialog was closed without pressing Start

    tracker = HandTracker()
    analyzer = HandAnalyzer()
    volume = actions.VolumeController()
    volume_gesture = ContinuousGesture(config.VOLUME_RATCHET)   # LEFT pointing, up/down
    # RIGHT pointing: joystick (default), tablet-style swipe or drag, see SCROLL_MODE
    scroll_gesture = {"joystick": JoystickScroll, "swipe": SwipeScroll}.get(
        config.SCROLL_MODE, ScrollGesture)()
    zoom_gesture = ZoomGesture()           # RIGHT near-pinch, thumb-index distance
    playpause_hold = HoldGesture()     # LEFT FIST held 2 s
    timer_hold = HoldGesture()         # LEFT OPEN PALM held 2 s
    reset_hold = HoldGesture()         # RIGHT OPEN PALM held 2 s = reset zoom to 100%
    screenshot_hold = HoldGesture()    # RIGHT FLAT HAND held 2 s = screenshot
    lock = GestureLock()               # only one gesture may act at a time
    message_text, message_until = None, 0.0   # short message shown on the preview
    timer = actions.CountdownTimer()   # runs in its own thread
    state = ControlState()
    show_debug = config.DEBUG_START_ON

    # Global hotkeys: these work even when another window has focus, and they
    # keep working while the camera is off.
    keyboard.add_hotkey(config.TOGGLE_HOTKEY, state.toggle)
    keyboard.add_hotkey(config.QUIT_HOTKEY, state.request_quit)
    print(f"Running. {config.TOGGLE_HOTKEY} = toggle control, "
          f"{config.QUIT_HOTKEY} or Esc = quit. Control starts OFF (camera off).")

    camera = None            # None = camera is released (webcam light off)
    hwnd = None              # Windows handle of the preview window
    window_setup_done = False   # have we minimized / pinned the window in this camera session?
    preview_rect = None      # where the user last left the preview window
    dark_since = None        # time when the frames first turned black
    failed_reads = 0         # consecutive frames the camera failed to give us

    def close_camera():
        """Release the camera and close the preview window."""
        nonlocal camera, hwnd, window_setup_done, preview_rect, dark_since, failed_reads
        if camera is not None:
            camera.release()
            camera = None
        saved = read_preview_rect(hwnd)       # remember where the window was
        if saved is not None:
            preview_rect = saved
        cv2.destroyAllWindows()
        cv2.waitKey(1)       # lets OpenCV actually close the window
        hwnd = None
        window_setup_done = False
        dark_since = None
        failed_reads = 0
        analyzer.reset()     # old hand history is meaningless after a pause
        volume_gesture.stop()    # every continuous action stops immediately
        scroll_gesture.reset()   # also forgets the remembered scroll direction
        zoom_gesture.stop()
        playpause_hold.reset()   # half-finished holds are cancelled
        timer_hold.reset()
        reset_hold.reset()
        screenshot_hold.reset()
        lock.reset()
        # (A running timer keeps counting: it is not a gesture in progress.)

    def handle_problem(message):
        """Close the camera, show the dialog once, then retry or switch OFF."""
        close_camera()
        choice = show_camera_error(tk_root, message, state)
        if choice == "off":
            state.set_enabled(False)
        # "retry": do nothing - the main loop sees camera is None and reopens it.

    try:
        while not state.quit_requested:
            # ---- Control OFF: camera must be fully released ----
            if not state.enabled:
                if camera is not None or hwnd is not None:
                    close_camera()
                time.sleep(config.OFF_LOOP_SLEEP_SECONDS)
                continue

            # ---- Control ON but camera not open yet: open it ----
            if camera is None:
                camera = open_camera()
                if camera is None:
                    handle_problem(config.CAMERA_MSG_CANNOT_OPEN)
                    continue
                create_preview_window(preview_rect)

            ok, frame = camera.read()
            if not ok:
                failed_reads += 1
                if failed_reads >= config.CAMERA_READ_FAIL_LIMIT:
                    handle_problem(config.CAMERA_MSG_LOST)
                continue
            failed_reads = 0

            # Camera covered (dark, or a finger over the lens) for
            # DARK_SECONDS in a row -> tell the user.
            if camera_looks_blocked(frame):
                if dark_since is None:
                    dark_since = time.monotonic()
                elif time.monotonic() - dark_since >= config.DARK_SECONDS:
                    handle_problem(config.CAMERA_MSG_DARK)
                    continue
            else:
                dark_since = None

            # Mirror FIRST, so everything after this sees the same image you do.
            if config.MIRROR_FRAME:
                frame = cv2.flip(frame, 1)

            height, width = frame.shape[:2]
            hands = analyzer.update(tracker.detect(frame), width, height)

            left = next((h for h in hands if h["label"] == "Left"), None)
            right = next((h for h in hands if h["label"] == "Right"), None)
            left_shape = left["shape"] if left is not None else None
            right_shape = right["shape"] if right is not None else None
            right_features = right["features"] if right is not None else None

            # ---- 1. Which gestures are being shown right now? ----
            # (The order of this dict only matters if two gestures appear on
            # exactly the same frame: the first one listed wins the lock.)
            zoom_start = right_shape == NEAR_PINCH or (
                config.ZOOM_START_FROM_SPREAD and right_shape == ZOOM_SPREAD)
            present = {
                # LEFT hand
                "Volume": left_shape in (POINTING, POINTING_SIDE),
                "Play/Pause": left_shape == FIST,
                # While a timer is running the palm does nothing, so it must
                # not take the lock either (it only shows a message, below).
                "Timer": left_shape == OPEN_PALM and not timer.running,
                # RIGHT hand
                "Scroll": right_shape in (POINTING, POINTING_SIDE),
                # zoom keeps going while the pose is held, not only during the pinch
                "Zoom": zoom_start or (zoom_gesture.active
                                        and ZoomGesture.in_zoom_pose(right_features)),
                "Reset zoom": right_shape == OPEN_PALM,
                "Screenshot": right_shape == FLAT_HAND,
            }
            gesture_hand = {"Volume": left, "Play/Pause": left, "Timer": left,
                            "Scroll": right, "Zoom": right, "Reset zoom": right,
                            "Screenshot": right}

            # ---- 2. ONE GESTURE AT A TIME: only the lock owner may act ----
            owner = lock.update(present)
            allowed = {name: is_present and name == owner for name, is_present in present.items()}
            for name, is_present in present.items():
                if is_present and name != owner and gesture_hand[name] is not None:
                    gesture_hand[name]["ignored"] = True     # shown on the preview

            # ---- 3. Run each gesture (blocked ones just see "shape not present") ----
            # LEFT POINTING / POINTING SIDE = volume (move the hand up / down)
            y = left["points"][config.VOLUME_TRACK_LANDMARK][1] if allowed["Volume"] else None
            started, steps = volume_gesture.update(allowed["Volume"], y)
            if started and config.GESTURE_SOUNDS:
                actions.play_beep([config.CLICK_BEEP])   # one click when it activates
            if steps:
                volume.change(steps)

            # RIGHT POINTING / POINTING SIDE = scroll (touchscreen style).
            # Joystick mode: hand above / below the starting height keeps scrolling.
            # Swipe mode: quick swipes fling the page, a right FIST stops the glide.
            # Drag mode: the page follows the hand, a right FIST resets the direction.
            # (Called every frame, so a glide keeps going after the hand stops pointing.)
            y = right["points"][config.SCROLL_TRACK_LANDMARK][1] if allowed["Scroll"] else None
            started, units = scroll_gesture.update(allowed["Scroll"], y, right_shape == FIST,
                                                   time.monotonic())
            if started and config.GESTURE_SOUNDS:
                actions.play_beep([config.CLICK_BEEP])
            if units:
                actions.scroll(units)

            # RIGHT NEAR-PINCH or ZOOM SPREAD, then spread / close = zoom (Ctrl + wheel)
            if allowed["Zoom"]:
                started, steps = zoom_gesture.update(right_shape if zoom_start else None,
                                                     right_features, time.monotonic())
            else:
                started, steps = zoom_gesture.update(None, None, time.monotonic())   # counts towards release
            if started and config.GESTURE_SOUNDS:
                actions.play_beep([config.CLICK_BEEP])
            if steps:
                actions.zoom(steps)

            # One-time gestures: hold for 2 seconds
            now = time.monotonic()
            hold_label, hold_progress, hold_waiting, notice = None, 0.0, False, None

            # LEFT FIST -> media play/pause
            progress, fired = playpause_hold.update(allowed["Play/Pause"], now)
            if allowed["Play/Pause"]:
                hold_label, hold_progress = "Play/Pause", progress
                hold_waiting = playpause_hold.waiting(now)
            if fired:
                actions.send_play_pause()
                if config.GESTURE_SOUNDS:
                    actions.play_beep(config.FIRE_BEEP)

            # LEFT OPEN PALM -> start the timer. While one is running the palm
            # only shows a message: no action, no beep, and it doesn't block
            # other gestures.
            if left_shape == OPEN_PALM and timer.running:
                notice = config.TIMER_RUNNING_TEXT
            progress, fired = timer_hold.update(allowed["Timer"], now)
            if allowed["Timer"]:
                hold_label, hold_progress = "Start timer", progress
                hold_waiting = timer_hold.waiting(now)
            if fired and timer.start() and config.GESTURE_SOUNDS:
                actions.play_beep(config.FIRE_BEEP)

            # RIGHT OPEN PALM -> reset zoom to 100%
            progress, fired = reset_hold.update(allowed["Reset zoom"], now)
            if allowed["Reset zoom"]:
                hold_label, hold_progress = "Reset zoom", progress
                hold_waiting = reset_hold.waiting(now)
            if fired:
                actions.reset_zoom()
                if config.GESTURE_SOUNDS:
                    actions.play_beep(config.FIRE_BEEP)

            # RIGHT FLAT HAND -> screenshot
            progress, fired = screenshot_hold.update(allowed["Screenshot"], now)
            if allowed["Screenshot"]:
                hold_label, hold_progress = "Screenshot", progress
                hold_waiting = screenshot_hold.waiting(now)
            if fired:
                try:
                    path = screenshot_without_preview(hwnd)
                    print(f"Screenshot saved: {path}")
                    message_text = f"{config.SCREENSHOT_SAVED_TEXT}: {os.path.basename(path)}"
                except Exception as error:     # e.g. disk full: tell the user, don't crash
                    print(f"Screenshot failed: {error}")
                    message_text = config.SCREENSHOT_FAILED_TEXT
                message_until = time.monotonic() + config.MESSAGE_SECONDS
                if config.GESTURE_SOUNDS:
                    actions.play_beep(config.FIRE_BEEP)
            if notice is None and time.monotonic() < message_until:
                notice = message_text

            for hand in hands:
                draw_hand(frame, hand)
            draw_status(frame, state.enabled, volume.percent, volume_gesture.active)
            if hold_label:
                draw_hold_bar(frame, hold_label, hold_progress, hold_waiting)
            if timer.running:
                draw_timer(frame, timer.remaining_seconds)
            if lock.owner is not None:
                draw_activity(frame, f"Active: {lock.owner}", config.COLOR_ACTIVE_TEXT, 1)
            if getattr(scroll_gesture, "centre", None) is not None:
                draw_scroll_centre(frame, scroll_gesture.centre)
            if notice:
                draw_notice(frame, notice)
            if show_debug:
                draw_debug(frame, hands)

            cv2.imshow(config.WINDOW_NAME, frame)

            # The window only exists after the first imshow, so find it now and
            # set it up once per camera session:
            #   Mode 2 -> minimize it to the taskbar.
            #   Mode 1 -> pin it above other windows (without stealing focus).
            if hwnd is None:
                hwnd = win32gui.FindWindow(None, config.WINDOW_NAME)
            if hwnd and not window_setup_done:
                if preview_mode == config.PREVIEW_MODE_MINIMIZE:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                elif config.PREVIEW_ALWAYS_ON_TOP:
                    win32gui.SetWindowPos(
                        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                window_setup_done = True

            key = cv2.waitKey(1) & 0xFF
            if key == config.QUIT_KEY:
                break
            if key in (ord(config.DEBUG_KEY.lower()), ord(config.DEBUG_KEY.upper())):
                show_debug = not show_debug
            # Stop if the window was closed with the X button. (We ask Windows
            # directly because OpenCV's "visible" flag is also 0 when minimized.)
            if hwnd and not win32gui.IsWindow(hwnd):
                break
    finally:
        # Always clean up, even if something crashed.
        keyboard.unhook_all_hotkeys()
        timer.stop()         # ends the timer thread
        tracker.close()
        close_camera()
        tk_root.destroy()    # on the main thread, where it was created
        print("Stopped.")


if __name__ == "__main__":
    main()

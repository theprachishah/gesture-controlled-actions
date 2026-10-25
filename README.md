# Hand Gesture Laptop Controller (Windows)

Control your laptop with hand gestures in front of the webcam: volume, scrolling,
zoom, play/pause, a 5-minute timer and screenshots. It uses MediaPipe to track
your hands, and it only acts while you have switched control ON.

---

## 1. Setup (one time)

You need **Windows**, a **webcam** and **Python 3.13** (the version this was built and tested with).

Open a terminal in the project folder and run:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The hand-tracking model file **`hand_landmarker.task`** must be in the project folder.
If it is missing, download it:

```
powershell -Command "Invoke-WebRequest -Uri https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task -OutFile hand_landmarker.task"
```

> **Why is MediaPipe pinned to 0.10.33?** On this laptop, Windows *Smart App Control*
> blocks the MediaPipe DLL in versions 0.10.30, 1.0.0 and 1.1.1
> (`WinError 4551 ... Application Control policy has blocked this file`).
> Version 0.10.33 is allowed. Don't upgrade MediaPipe without checking this.

## 2. Run it

```
.venv\Scripts\python.exe main.py
```

1. A small window asks how the preview should behave:
   - **Mode 1 - Show preview:** a small camera window stays on top of other windows
     (bottom right corner). You can move and resize it. It only minimizes if you
     press its own minimize button.
   - **Mode 2 - Minimize:** the preview stays minimized in the taskbar. Click it to look.
2. Control starts **OFF**, with the camera off.
3. Press **Ctrl+Alt+G** to turn control **ON**. You'll hear the "Speech On" sound and the camera starts.

| Key | What it does |
|---|---|
| **Ctrl+Alt+G** | Turn control ON / OFF (works from any window). OFF = camera fully off. |
| **Ctrl+Alt+Q** | Quit the program (works from any window) |
| **Esc** | Quit (only while the preview window has focus) |
| **D** | Show / hide the debug numbers on the preview |

---

## 3. Gesture cheat sheet

Hold your hand **fully inside the frame**. A hand that is partly outside turns
**grey** and is ignored. A shape only counts after it has been steady for a few
frames, so waving a hand through the picture does nothing.

### LEFT hand

| Gesture | Shape | What happens |
|---|---|---|
| **Volume** | ☝️ **Pointing**: index up (or sideways, like a slider), other fingers curled, thumb folded over them | Move the hand **up = louder**, **down = quieter** (4% per step) |
| **Play / Pause** | ✊ **Fist**: all fingers curled | Hold **1.5 s** to press the media play/pause key |
| **Timer** | 🖐️ **Open palm**: fingers spread, thumb out, palm facing the camera, hand upright | Hold **1.5 s** to start a **5-minute timer**. The countdown shows top right. When it ends you get a notification and a short alarm. If a timer is already running: "Timer already running", nothing else happens. |

### RIGHT hand

| Gesture | Shape | What happens |
|---|---|---|
| **Scroll** | ☝️ **Pointing**: index up or sideways, other fingers curled, thumb folded | **Joystick:** where your hand is when you start pointing is the **centre** (the preview shows a "stop" band). Hold the hand **above** it = the page keeps gliding **down** (like a tablet swipe up), **below** = keeps gliding **up**. Further away = faster. Back to the centre = stop. |
| **Zoom** | Start from a 🤏 **near-pinch** *or* a **"C" shape** (thumb and index apart), other 3 fingers curled | **Joystick:** where your fingers are when zoom starts is the **centre**. Open **wider** than that = keeps zooming **in**, close **narrower** = keeps zooming **out**, back to the centre = stop. Further from the centre = faster. Start from the **C** if you may want to zoom out. |
| **Reset zoom** | 🖐️ **Open palm** | Hold **1.5 s** to press **Ctrl+0** (100% in browsers / Office; "fit" in many photo viewers) |
| **Screenshot** | 🫳 **Flat hand**: four fingers together pointing sideways, palm facing down (like over a table) | Hold **1.5 s** to save a full-screen PNG to **Pictures\Screenshots** as `gesture_YYYY-MM-DD_HH-MM-SS.png` |

Zoom ends when you straighten your middle, ring or pinky finger, fold your thumb
over your fingers, or move the hand out of the frame. (`ZOOM_MODE` in `config.py`
also offers "ratchet" and "both" styles.)

### Good to know

- **One gesture at a time.** The first gesture you start "locks" control.
  Everything else, including the other hand, is ignored (the preview shows
  **(ignored)**) until you release that gesture. The top right shows
  **Active: <gesture>**. The only exception: a left open palm while a timer is
  already running doesn't block anything.
- **Hold gestures** (play/pause, timer, reset zoom, screenshot): a bar fills while you
  hold. If the shape breaks, the bar restarts. After firing, the same gesture waits
  **3 s** and you must **lower your hand** before it can fire again (holding a fist
  doesn't keep toggling play/pause). A grey bar means "waiting".
- **Scroll and zoom go to the window under your mouse pointer.** Reset zoom first
  brings that window to the front, then presses Ctrl+0.
- **Screenshots hide the preview** for a moment, so it isn't in the picture.
- Gestures are **silent** (`GESTURE_SOUNDS = False`). You only hear control ON/OFF,
  the camera-problem ding and the timer alarm.

---

## 4. Camera problems

If control is ON and the camera **can't be opened** (another app is using it, no
permission) or is **covered** (a finger, hand or privacy shutter, for about 3 seconds),
a dialog pops up with a ding:

- **Retry**: try the camera again.
- **Turn off**: switch control OFF.

---

## 5. Tuning (`config.py`)

**Every number lives in `config.py`.** Change it there, then restart the program
(changes are only read at start). The ones you're most likely to want:

| Setting | Now | Meaning |
|---|---|---|
| `STEP_DISTANCE` | 0.04 | How far (fraction of frame height) you move for one volume step. Smaller = more sensitive. |
| `VOLUME_STEP_PERCENT` | 4 | Volume change per step |
| `SCROLL_MODE` | joystick | "joystick" (hold above/below the centre), "swipe" (tablet-style fling) or "drag" (page follows the hand) |
| `SCROLL_JOYSTICK_SPEED` / `SCROLL_JOYSTICK_MAX_SPEED` | 6000 / 2400 | How fast joystick scroll speeds up, and its top speed |
| `SCROLL_JOYSTICK_DEADZONE` | 0.04 | Size of the "stop" band around the centre |
| `SWIPE_GAIN` (swipe mode) | 2000 | How far a swipe flings the page (bigger = further) |
| `SWIPE_DECAY_SECONDS` (swipe mode) | 0.5 | How long the glide lasts (bigger = longer) |
| `SWIPE_MIN_DISTANCE` (swipe mode) | 0.08 | How big a quick movement must be to count as a swipe |
| `SCROLL_SPEED` | 9000 | Drag mode only: scroll amount per frame height of hand movement |
| `SCROLL_DIRECTION_MEMORY_SECONDS` | 2.0 | Drag mode only: how long the scroll direction is remembered |
| `SCROLL_INVERT` | False | False = touchscreen style, True = mouse-wheel style |
| `SCROLL_RATCHET` | True | Drag mode only: first movement fixes the scroll direction |
| `VOLUME_RATCHET` | False | Same ratchet idea for volume (off = up and down both work in one go) |
| `ZOOM_DISTANCE_STEP` | 0.20 | Thumb-index change (in hand sizes) per zoom notch. Smaller = faster zoom. |
| `PINCH_START_DISTANCE` | 0.35 | How close thumb and index must be to count as a near-pinch |
| `ZOOM_START_FROM_SPREAD` | True | Allow starting zoom from the "C" shape (needed for zoom-out) |
| `ZOOM_MODE` | joystick | "joystick" (hold away from the centre to keep zooming), "ratchet" or "both" |
| `ZOOM_JOYSTICK_SPEED` / `ZOOM_JOYSTICK_MAX_RATE` | 8 / 6 | How fast joystick zoom goes |
| `HOLD_SECONDS` | 1.5 | Hold time for play/pause, timer, reset zoom, screenshot |
| `COOLDOWN_SECONDS` | 3.0 | Wait after a hold gesture fires |
| `TIMER_MINUTES` | 5 | Timer length |
| `TIMER_DONE_SOUND_SECONDS` | 2.8 | How long the alarm plays (includes about 1 s Windows sound delay; don't go below about 1.5) |
| `GESTURE_SOUNDS` | False | True = click/beep when a gesture starts or fires |
| `SHAPE_STABLE_FRAMES` | 5 | Frames a shape must be steady before it counts |
| `RELEASE_FRAMES` | 5 | Frames without the shape before a gesture ends |
| `PREVIEW_WIDTH` / `PREVIEW_HEIGHT` | 520 / 390 | Starting size of the preview window |
| `PREVIEW_ALWAYS_ON_TOP` | True | Keep the Mode 1 preview above other windows |

Shape thresholds (`THUMB_FOLD_DISTANCE`, `OPEN_PALM_MIN_SPREAD_DEG`, and so on) were
measured on this laptop and hand. The comments next to them show the measured
values. Press **D** to see the live numbers if a shape isn't detected.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| Left/Right labels are swapped | Flip `SWAP_HANDEDNESS` in `config.py` (on this laptop it must be `True`) |
| A shape isn't detected | Press **D** and compare the numbers with the thresholds in `config.py`. Keep the hand fully inside the frame. |
| Open palm not detected | Spread your fingers wide and stretch your thumb out, with the palm facing the camera |
| Zoom doesn't react | Keep middle, ring and pinky curled, and keep the hand away from the frame edges when spreading wide |
| Reset zoom / play-pause does nothing in an app | That app may use different shortcuts. Change `RESET_ZOOM_KEYS`. |
| "Camera looks covered" in a dim room | Lower `DARK_BRIGHTNESS_THRESHOLD` a little (keep it above 18) |
| A hotkey doesn't work | Run the terminal as Administrator (the `keyboard` library sometimes needs it) |
| Edits to `config.py` have no effect | Quit (Ctrl+Alt+Q) and start the program again |

---

## 7. Files

| File | What it does |
|---|---|
| `main.py` | Starts everything: startup dialog, hotkeys, camera loop, the one-gesture lock, deciding which gesture runs, drawing the preview |
| `gestures.py` | Understands hands: MediaPipe tracking, smoothing, measuring fingers, deciding the shape, and the logic for continuous gestures, hold gestures, zoom and the lock |
| `actions.py` | Does things to the computer: sounds, volume, scroll, zoom, play/pause, reset zoom, timer, screenshots |
| `config.py` | Every setting and threshold |
| `requirements.txt` | Library versions |
| `hand_landmarker.task` | MediaPipe's hand model |
| `PLAN.md` | The original project plan, plus the changes made along the way |

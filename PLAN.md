# Project: Hand Gesture Laptop Controller (Windows)

## Environment
- OS: Windows
- Camera: built-in laptop webcam (camera index 0, 640x480)
- Python: 3.11 recommended (MediaPipe support). Check my version first; if it is not 3.9 to 3.12, tell me before continuing.
- Use a virtual environment in the project folder: python -m venv .venv
- Put all libraries in requirements.txt with pinned versions.

## Libraries
- opencv-python: camera capture and preview window
- mediapipe: hand landmark detection (21 landmarks per hand, max 2 hands). Use whichever Hands API works with the pinned version (legacy solutions.hands or the Tasks HandLandmarker) and tell me which one you chose.
- pycaw + comtypes: Windows master volume (get and set level)
- pyautogui: scroll, Ctrl+scroll zoom, media play/pause key
- keyboard: global hotkeys that work even when another window is focused
- winotify: Windows toast notification when the timer ends
- pywin32: minimize the preview window to the taskbar, find the real Pictures folder
- Pillow (ImageGrab) or mss: screenshots
- winsound (built-in): beeps
- tkinter (built-in): startup choice dialog

## File structure
- main.py: startup, camera loop, hotkeys, state machine, gesture routing, preview drawing
- gestures.py: hand shape classification and movement tracking
- actions.py: volume, scroll, zoom, play/pause, timer, screenshot, sounds
- config.py: every threshold, timing, step size, hotkey and setting
- requirements.txt
- PLAN.md (this document)
- README.md: how to set up and run, plus a gesture cheat sheet

## Overall behavior
- On launch, show a small tkinter dialog asking for the preview mode:
  - Mode 1 "Show preview": the camera preview window is visible whenever control is ON.
  - Mode 2 "Minimize": the preview window stays minimized in the taskbar (I can click it to look).
- Control starts OFF.
- Ctrl+Alt+G toggles control ON/OFF from anywhere.
  - Turning ON: rising two-tone beep.
  - Turning OFF: falling two-tone beep. All continuous actions stop immediately.
- Ctrl+Alt+Q quits the program cleanly (releases camera, closes windows, stops timer thread). Pressing Esc in the preview window also quits.
- While OFF: the camera may keep running, but NO action is ever triggered.

## Handedness
- Flip the camera frame horizontally first (mirror view) so "Left" and "Right" match MY real hands.
- In Step 1, display the detected label on screen so I can verify it is correct.
- If the labels are reversed, fix it with a config flag SWAP_HANDEDNESS.
- Each gesture only works with its assigned hand. The same shape on the other hand does that hand's action, or nothing.

## Gesture spec

### LEFT HAND

1. Volume up/down (continuous)
   - Shape: POINTING = index finger extended and pointing up; middle, ring, pinky curled; thumb folded over the curled fingers.
   - Movement: move the hand up = volume up, move it down = volume down.
   - Vertical movement only; ignore horizontal movement.
   - ADDED (user request, Step 4): a second shape also works for volume: POINTING SIDE = same finger/thumb pose but the index finger points horizontally to the RIGHT (like a slider handle). Moving that hand up/down changes the volume the same way. Left hand only.

2. Play/pause (one-time)
   - Shape: CLOSED FIST = all five fingers curled.
   - Hold for 2 seconds, then send the media play/pause key.

3. Open timer (one-time)
   - Shape: OPEN PALM = upright hand, all five fingers extended and spread, fingers pointing up, palm facing the camera.
   - Hold for 2 seconds, then start a 5-minute countdown timer.
   - If a timer is already running, IGNORE the gesture: show "Timer already running" on the preview, no beep, no action.

### RIGHT HAND

4. Scroll (continuous, touchscreen style)
   - Shape: POINTING = index finger extended and pointing up; middle, ring, pinky curled; thumb folded over the curled fingers.
   - Direction is like a phone screen: moving the finger UP pushes the page content up, so the view moves DOWN the page (towards the bottom). Moving the finger DOWN moves the view UP the page (towards the top).
   - Set SCROLL_INVERT in config.py so this touchscreen behavior is the default, with a comment explaining which value gives which direction.
   - FINAL (Step 10, user request): scroll is JOYSTICK by default (SCROLL_MODE "joystick"): the hand
     height when pointing starts is the centre; above = keeps scrolling down the page, below = up,
     faster further away (capped), centre band = stop. Swipe and drag styles remain as options.
   - (before that) scroll was TABLET-STYLE SWIPE with momentum
     (SCROLL_MODE "swipe"): a quick swipe flings the page, it glides and slows down; slow
     movements (bringing the hand back) do nothing; opposite direction ignored for 0.8 s after a
     swipe; a right fist stops the glide. The drag+ratchet style below is kept as SCROLL_MODE "drag".
   - (earlier) RATCHET scroll (SCROLL_RATCHET True). The first step of a scroll
     gesture fixes its direction; moving the other way is a re-grip (no scroll), so the hand can come
     back down and push again without leaving the frame. Reverse by ending the gesture (right fist for
     a moment) and pointing again. Same option exists for volume (VOLUME_RATCHET, off by default).
   - Vertical movement only; ignore horizontal movement.

5. Zoom in/out (continuous)
   - Shape: thumb and index engaged; middle, ring, pinky curled throughout.
   - Zoom mode STARTS when the thumb tip and index tip are ALMOST touching (very close, not necessarily in contact). Use a generous config value PINCH_START_DISTANCE, normalized by hand size, so a near-pinch counts.
   - While in zoom mode: spreading thumb and index apart = zoom in; bringing them back to almost touching = zoom out.
   - Zoom amount is based on the CHANGE in thumb-to-index distance, normalized by hand size (distance from wrist to middle-finger base knuckle), so it works at any distance from the camera.
   - The hand may be rotated (index pointing sideways or forward), so use only normalized distances, never raw x/y directions, for the zoom logic.
   - Zoom is sent as Ctrl + mouse scroll.
   - Zoom mode ends when middle/ring/pinky extend or the hand leaves the frame.

   - CHANGED (Step 10 tuning, user reported zoom-out not working): zoom can ALSO start from a
     ZOOM SPREAD pose (thumb and index apart, others curled, thumb not folded), so zoom-out works
     like a phone: start spread, close to pinch. Config ZOOM_START_FROM_SPREAD (True). Zoom now
     ends on a clearly folded thumb (ZOOM_END_THUMB_DISTANCE 0.75) to avoid false ends.
   - CHANGED AGAIN (Step 10, user request): JOYSTICK zoom (ZOOM_MODE "joystick"): the distance when
     zoom starts is the centre; wider = keep zooming in, narrower = keep zooming out, faster the
     further away, centre = stop. "ratchet" and "both" remain as options.
   - (earlier) RATCHET zoom. The start shape fixes the
     direction for the session: from the pinch = zoom in only, from the spread = zoom out only.
     Moving the other way is a "re-grip" (no zoom), so zooming can continue without leaving the
     frame. Switch direction by ending the session (straighten the middle finger briefly).
   - ADDED (user request, Step 7): RIGHT hand OPEN PALM (same shape as the left-hand timer gesture) held 2 s resets zoom to 100% by sending Ctrl+0. Uses the normal one-time rules (2 s hold, 3 s cooldown, release before repeat).

6. Screenshot (one-time)
   - Shape: FLAT HORIZONTAL HAND = index, middle, ring, pinky all extended and held TOGETHER (not spread), fingers pointing sideways, palm facing DOWN (like holding a hand out flat over a table). Thumb rests alongside the index finger.
   - The camera will mostly see the back or the edge of the hand, so do NOT require the palm to face the camera. Accept palm facing down or slightly toward/away from the camera.
   - Detection: all four fingers extended + the vector from wrist to middle-finger base knuckle is within HORIZONTAL_ANGLE_TOLERANCE degrees of horizontal. Do not require fingers to be spread.
   - Hold for 2 seconds, then save a full-screen screenshot as PNG.
   - Save location: the Windows Pictures\Screenshots folder. Find the real Pictures folder with the Windows known-folder API (it may be redirected to OneDrive). Create the Screenshots folder if missing.
   - Filename: gesture_YYYY-MM-DD_HH-MM-SS.png
   - In Step 3, specifically test how reliably MediaPipe tracks this edge-on hand and tell me if it is unstable, with suggestions.

### Keeping right-hand shapes apart
- POINTING (scroll): index extended, thumb FOLDED over the curled fingers (thumb tip close to the palm / middle-finger area, relative to hand size).
- ZOOM: thumb NOT folded; starts from a near-pinch between thumb tip and index tip.
- SCREENSHOT: four fingers extended together, pointing sideways.
- Put all these thresholds in config.py.

## Finger state detection
- Index, middle, ring, pinky: "extended" if the tip is farther from the wrist than the PIP joint. Use distances, not just y-coordinates, so it works when the hand is rotated (e.g. the flat horizontal hand).
- Thumb: "extended" vs "folded" based on the thumb tip distance from the index base knuckle, normalized by hand size.
- Smooth landmark positions with an exponential moving average (SMOOTHING_ALPHA).
- A shape only counts after it has been stable for SHAPE_STABLE_FRAMES consecutive frames.

## Safety and false-trigger rules
1. Confidence: min detection confidence 0.7, min tracking confidence 0.6 (config).
2. Position filter: ignore a hand if any landmark is outside the frame margin (FRAME_MARGIN, e.g. 0.02 to 0.98 of the frame). A hand only partly visible never triggers anything.
3. Hand passing through: continuous gestures only start after the shape is stable. Movement before that is ignored.
4. ONE GESTURE AT A TIME: the first gesture that becomes active "locks" control. All other gestures, including the other hand, are ignored until the active gesture is released (shape changes or hand leaves the frame) for RELEASE_FRAMES frames.
5. One-time gestures (play/pause, timer, screenshot):
   - Need a continuous 2-second hold (HOLD_SECONDS). If the shape breaks, the hold timer resets.
   - After firing, a 3-second cooldown (COOLDOWN_SECONDS) for that gesture.
   - After firing, the hand must release the shape before the same gesture can fire again (holding a fist does not repeat play/pause).
6. Continuous gestures (volume, scroll, zoom): when the gesture starts, record the starting position (or starting thumb-index distance for zoom) as the anchor. Each time it changes by one step from the anchor, send ONE step and move the anchor. Changes smaller than DEADZONE are ignored to prevent jitter.

## Speeds ("medium, balanced" defaults, all in config.py)
- VOLUME_STEP_PERCENT = 4 (percent per step)
- SCROLL_CLICKS_PER_STEP = 3
- ZOOM_DISTANCE_STEP = 0.15 (normalized distance change per one Ctrl+scroll notch)
- PINCH_START_DISTANCE = generous near-pinch value, tune in Step 3
- STEP_DISTANCE = 0.04 (fraction of frame height, for volume and scroll)
- DEADZONE = 0.01
- SMOOTHING_ALPHA = 0.5
- SHAPE_STABLE_FRAMES = 5
- RELEASE_FRAMES = 5
- HOLD_SECONDS = 2.0
- COOLDOWN_SECONDS = 3.0
- TIMER_MINUTES = 5
- HORIZONTAL_ANGLE_TOLERANCE = 30 (degrees)
- FRAME_MARGIN = 0.02
- SWAP_HANDEDNESS = False
- SCROLL_INVERT = value that gives touchscreen-style scrolling
- TOGGLE_HOTKEY = "ctrl+alt+g"
- QUIT_HOTKEY = "ctrl+alt+q"

## Sounds (winsound, non-blocking so the camera loop never freezes)
- Control ON: rising two-tone beep
- Control OFF: falling two-tone beep
- One-time gesture fired (play/pause, timer start, screenshot): short click/beep
- Continuous gestures: a short click only when the gesture first activates, not on every step
- Timer finished: longer beep pattern

## Timer
- Runs in a background thread so the camera loop is never blocked.
- Countdown (MM:SS) is shown on the preview window.
- When it ends: Windows toast notification "Timer done - 5 minutes are up" plus the timer-finished beep.

## Preview window (OpenCV)
Show on the mirrored camera image:
- Control state: ON (green) / OFF (red)
- Hand landmarks drawn, with the hand label (Left/Right)
- Current detected gesture name
- Hold progress bar for one-time gestures (fills over 2 seconds)
- Current volume level (percent)
- Timer countdown if running
- Debug line (toggle with the D key): finger states, thumb fold state, thumb-index distance, palm angle

## Build steps (one at a time, stop after each)
1. Setup and tracking: venv, requirements.txt, camera preview, mirrored frame, landmarks drawn, Left/Right labels shown. Test: I check the labels match my real hands.
2. Control state: startup preview-mode dialog, Ctrl+Alt+G toggle, Ctrl+Alt+Q and Esc quit, ON/OFF beeps, ON/OFF shown on the preview. Test: toggle works while another window is focused.
3. Shape detection: classify POINTING, FIST, OPEN PALM, NEAR-PINCH/ZOOM, FLAT HORIZONTAL HAND; show the name live, plus the debug line. No actions yet. Test: I try each shape with each hand, including the edge-on flat hand.
4. Left-hand volume: continuous volume with anchor/step logic and the volume level on screen.
5. Left-hand one-time gestures: play/pause and timer, with the 2-second hold, progress bar, cooldown, release rule, "ignore if timer running", toast notification.
6. Right-hand scroll, touchscreen style.
7. Right-hand zoom from a near-pinch.
8. Right-hand screenshot, saved to the correct Pictures\Screenshots folder.
9. One-gesture-at-a-time lock and all false-trigger rules checked end to end.
10. Tuning session: help me adjust config.py values based on how it feels. Then write README.md with setup steps and a gesture cheat sheet.

## Start now
Save this as PLAN.md, check my Python version, then do Step 1 only and tell me how to test it.

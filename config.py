"""
config.py - every tunable number and setting for the gesture controller.

If you want to change how the program behaves (camera, thresholds, speeds,
colours...), change it HERE. No other file should contain "magic numbers".
"""

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0          # 0 = built-in laptop webcam
FRAME_WIDTH = 640         # requested capture width in pixels
FRAME_HEIGHT = 480        # requested capture height in pixels
MIRROR_FRAME = True       # flip horizontally so the preview acts like a mirror

# ---------------------------------------------------------------------------
# MediaPipe hand tracking (Tasks HandLandmarker API)
# ---------------------------------------------------------------------------
MODEL_PATH = "hand_landmarker.task"   # model file in the project folder
MAX_HANDS = 2
MIN_DETECTION_CONFIDENCE = 0.7   # how sure MediaPipe must be to FIND a new hand
MIN_PRESENCE_CONFIDENCE = 0.6    # how sure it must be that the hand is still there
MIN_TRACKING_CONFIDENCE = 0.6    # how sure it must be to keep TRACKING a hand

# If the on-screen "Left"/"Right" labels are the opposite of your real hands,
# set this to True and they will be swapped.
SWAP_HANDEDNESS = True

# ---------------------------------------------------------------------------
# Preview window
# ---------------------------------------------------------------------------
WINDOW_NAME = "Gesture Controller"
QUIT_KEY = 27             # key code for Esc (quits from the preview window)

# Preview window size and behaviour. The window can still be moved and resized
# by hand; where you leave it is remembered while the program runs.
PREVIEW_WIDTH = 520       # starting size in pixels (the camera image is 640x480)
PREVIEW_HEIGHT = 390
PREVIEW_MARGIN = 20       # gap from the screen edge for the starting position (bottom right)
PREVIEW_TASKBAR_ALLOWANCE = 60   # extra gap at the bottom so the window clears the taskbar
# Mode 1 only: keep the preview above other windows so clicking elsewhere never
# hides it. It still minimizes if you press its own minimize button.
PREVIEW_ALWAYS_ON_TOP = True

# Colours are in OpenCV's BGR order (Blue, Green, Red), not RGB.
COLOR_LEFT_HAND = (255, 128, 0)     # blue-ish for the left hand
COLOR_RIGHT_HAND = (0, 165, 255)    # orange for the right hand
COLOR_LANDMARK_POINT = (255, 255, 255)
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_BG = (0, 0, 0)

LANDMARK_RADIUS = 4       # pixels
LINE_THICKNESS = 2        # pixels
FONT_SCALE = 0.7
FONT_THICKNESS = 2
LABEL_OFFSET_PX = 20      # how far below the wrist the Left/Right label sits
TEXT_PADDING_PX = 4       # padding around text backgrounds

# ---------------------------------------------------------------------------
# Control state and hotkeys
# ---------------------------------------------------------------------------
TOGGLE_HOTKEY = "ctrl+alt+g"   # turns control ON/OFF from any window
QUIT_HOTKEY = "ctrl+alt+q"     # quits the whole program from any window

# Preview modes chosen in the startup dialog
PREVIEW_MODE_SHOW = "show"         # window stays visible
PREVIEW_MODE_MINIMIZE = "minimize" # window stays minimized in the taskbar

# Status text on the preview
COLOR_STATE_ON = (0, 200, 0)       # green (BGR)
COLOR_STATE_OFF = (0, 0, 255)      # red (BGR)
STATUS_TEXT_X = 10                 # pixels from the left edge
STATUS_TEXT_Y = 30                 # pixels from the top edge
HINT_TEXT_Y_OFFSET = 12            # pixels above the bottom edge for the hotkey hint
HINT_FONT_SCALE = 0.5

# ---------------------------------------------------------------------------
# Startup dialog (tkinter)
# ---------------------------------------------------------------------------
DIALOG_TITLE = "Gesture Controller"
DIALOG_PADDING = 12                # pixels around dialog widgets

# ---------------------------------------------------------------------------
# Sounds
# ---------------------------------------------------------------------------
# Windows sound files. If a file is missing we play ONE short beep instead.
SOUND_ON = r"C:\Windows\Media\Speech On.wav"     # control turned ON
SOUND_OFF = r"C:\Windows\Media\Speech Off.wav"   # control turned OFF
SOUND_DIALOG = r"C:\Windows\Media\ding.wav"      # camera problem dialog appeared
FALLBACK_BEEP = (800, 150)   # (frequency in Hz, length in ms)

# ---------------------------------------------------------------------------
# Camera problems
# ---------------------------------------------------------------------------
# A frame is "black" if its average brightness (0 = pure black, 255 = pure
# white) is below this. If frames stay black for DARK_SECONDS, we assume the
# camera is covered or the privacy shutter is closed.
# Measured on this laptop: covered camera = about 18, normal room = about 143.
# (A covered lens is dark gray, not pure 0, so the threshold must be above 18.)
# If you use the program in a very dim room and get false "covered" dialogs,
# lower this a little (but keep it above 18).
DARK_BRIGHTNESS_THRESHOLD = 30

# A FINGER over the lens is not dark (light shines through it) but the image
# becomes flat and very red. We call the camera "covered by a finger/hand" when
# BOTH are true. Measured on this laptop:
#   normal room: detail (std) = 35,  red ratio = 1.1
#   finger:      detail (std) = 9.5, red ratio = 2.4
# Both numbers are checked together so a plain wall alone doesn't trigger it.
FLAT_DETAIL_THRESHOLD = 20       # detail below this = flat image
RED_RATIO_THRESHOLD = 1.7        # red / average(blue, green) above this = very red
BLOCK_CHECK_SIZE = (80, 60)      # frames are shrunk to this before measuring (fast)
DARK_SECONDS = 3.0
CAMERA_READ_FAIL_LIMIT = 30      # this many failed reads in a row = camera lost
OFF_LOOP_SLEEP_SECONDS = 0.05    # how long the loop naps while control is OFF

CAMERA_MSG_CANNOT_OPEN = ("Camera not available - it may be blocked, "
                          "covered, or used by another app.")
CAMERA_MSG_DARK = ("The camera looks covered - something (like a finger) may be "
                   "over the lens, or the privacy shutter may be closed.")
CAMERA_MSG_LOST = "The camera stopped sending pictures - it may have been unplugged or taken by another app."
CAMERA_DIALOG_TITLE = "Camera problem"
CAMERA_DIALOG_POLL_MS = 100      # how often the dialog checks if it should close itself

# ---------------------------------------------------------------------------
# Hand shape detection (Step 3)
# ---------------------------------------------------------------------------
# "Hand size" = distance from the wrist to the middle finger's base knuckle.
# Most distances below are divided by hand size, so they work the same whether
# your hand is close to the camera or far away.

USE_DEPTH = True             # True = use 3D distances (x, y and depth z); False = 2D only
SMOOTHING_ALPHA = 0.5        # 0..1, how much each new frame counts (lower = smoother but slower)
SHAPE_STABLE_FRAMES = 5      # a shape must be seen this many frames in a row to count
FRAME_MARGIN = 0.02          # hands with any point outside 2%..98% of the frame are ignored

# A finger (index/middle/ring/pinky) is EXTENDED if
#   distance(wrist, fingertip) > distance(wrist, middle joint) * FINGER_EXTENDED_RATIO
# Straight finger is about 1.3, fully curled about 0.6.
FINGER_EXTENDED_RATIO = 1.15

# FIST: every fingertip is close to the wrist: distance(wrist, tip) / hand size
# below this. (A curled finger is about 0.8, a near-pinch index is about 1.4.)
FIST_MAX_REACH = 1.1

# THUMB: FOLDED if distance(thumb tip, PINKY base knuckle) / hand size is below
# this, otherwise EXTENDED.
# (The plan said "index base knuckle", but measured on your hand that only
# separated the two cases by 0.09. The pinky knuckle separates them by 0.43.)
# Measured: thumb out (open palm) 1.12-1.27, folded (pointing) 0.57-0.69,
#           near-pinch 0.95-1.03 (thumb not folded, correct).
THUMB_FOLD_DISTANCE = 0.9

# NEAR-PINCH (zoom start): distance(thumb tip, index tip) / hand size below this.
# Touching is about 0.1, so this is generous on purpose.
PINCH_START_DISTANCE = 0.35

# OPEN PALM: the angle (degrees) between the index finger and the pinky must be
# above this, i.e. fingers spread like a fan.
# Measured: spread wide 42-48, fingers held together 9-15.
OPEN_PALM_MIN_SPREAD_DEG = 25
REQUIRE_PALM_FACING_CAMERA = True   # open palm only counts if the palm faces the camera

# Angles in degrees. 90 = pointing straight up, 0 or 180 = sideways.
UPRIGHT_ANGLE_TOLERANCE = 35        # open palm: hand within this of straight up
POINTING_ANGLE_TOLERANCE = 45       # pointing: index finger within this of straight up
HORIZONTAL_ANGLE_TOLERANCE = 30     # flat hand: hand within this of horizontal
SIDE_POINTING_ANGLE_TOLERANCE = 35    # sideways pointing: index within this of horizontal (pointing right OR left)

# ---------------------------------------------------------------------------
# Debug overlay (press D in the preview to show/hide)
# ---------------------------------------------------------------------------
DEBUG_KEY = "d"
DEBUG_START_ON = True        # show the debug lines when the program starts
DEBUG_FONT_SCALE = 0.45
DEBUG_TEXT_Y = 60            # pixels from the top for the first debug line
DEBUG_LINE_SPACING = 22      # pixels between debug lines
COLOR_HAND_PARTIAL = (128, 128, 128)   # grey = hand partly outside the frame (ignored)
COLOR_SHAPE_TEXT = (0, 255, 255)       # yellow, the detected shape name

# ---------------------------------------------------------------------------
# Continuous gestures: volume (Step 4), later scroll and zoom
# ---------------------------------------------------------------------------
# Anchor/step rule: when the gesture starts we remember the hand's height (the
# "anchor"). Every time the hand moves STEP_DISTANCE away from the anchor we
# send ONE step and move the anchor by one step. Movement smaller than
# DEADZONE is ignored completely.
STEP_DISTANCE = 0.04     # fraction of the frame HEIGHT per step (volume and scroll)
DEADZONE = 0.01          # fraction of the frame HEIGHT; smaller movements are ignored
RELEASE_FRAMES = 5       # shape must be missing this many frames in a row to end the gesture

# RATCHET (like re-gripping): the FIRST step of a gesture fixes its direction.
# Moving the other way is then a "re-grip" that does nothing, so when your hand
# reaches the top (or bottom) of the camera picture you can bring it back and
# push again without leaving the frame. To change direction, end the gesture
# for a moment (right hand: make a fist; left hand: lower or change the hand
# shape), then point again.
SCROLL_RATCHET = True     # False = old behaviour: up and down both scroll in one gesture
VOLUME_RATCHET = False    # same idea for volume (off: moving down lowers volume again)

VOLUME_STEP_PERCENT = 4          # volume change per step, in percent
VOLUME_TRACK_LANDMARK = 9        # which hand point to follow (9 = base of middle finger, steady)
VOLUME_POLL_SECONDS = 0.5        # how often to re-read the real volume (catches changes made elsewhere)
COLOR_VOLUME_TEXT = (255, 200, 0)    # volume readout on the preview (BGR)
VOLUME_TEXT_Y_OFFSET = 36            # pixels below the Control status line

# Sounds for your gestures (the click when volume/scroll/zoom starts, and the beep
# when play/pause, timer or screenshot fires). False = silent gestures.
# This does NOT affect the control ON/OFF sounds, the camera-problem ding or the
# timer-finished alarm.
GESTURE_SOUNDS = False

# Short click played when a continuous gesture first activates: (Hz, ms)
CLICK_BEEP = (1000, 40)

# ---------------------------------------------------------------------------
# One-time gestures: play/pause and timer (Step 5), later screenshot
# ---------------------------------------------------------------------------
HOLD_SECONDS = 1.5        # how long the shape must be held without a break (tuned down from 2.0)
COOLDOWN_SECONDS = 3.0    # after firing, the same gesture is ignored for this long
# (After firing you must ALSO release the shape before it can fire again.)

TIMER_MINUTES = 5
TIMER_DONE_TITLE = "Timer done"
TIMER_DONE_MESSAGE = f"Timer done - {TIMER_MINUTES} minutes are up"
TOAST_APP_ID = "Gesture Controller"     # name shown on the Windows notification
TIMER_RUNNING_TEXT = "Timer already running"

# pyautogui safety/speed settings
PYAUTOGUI_FAILSAFE = False   # True would crash the program if the mouse touches a screen corner
PYAUTOGUI_PAUSE = 0          # seconds pyautogui waits after each key press (0 = no delay)
KEY_PLAY_PAUSE = "playpause" # pyautogui's name for the media play/pause key

# Sounds: lists of (frequency in Hz, length in ms)
FIRE_BEEP = [(1200, 90)]                                             # a one-time gesture fired
SOUND_TIMER_DONE = r"C:\Windows\Media\Alarm04.wav"   # played when the timer ends
# The alarm file is 4.6 s long. We stop it this many seconds after asking Windows to
# play it. On this laptop the sound only starts coming out about 1 s after the
# request (measured with a speaker peak meter), (the delay varies 1.0-1.6 s), so 2.8 s = about 1.2-1.8 s of audible
# alarm. Do NOT go below ~1.2 or you will hear nothing at all.
TIMER_DONE_SOUND_SECONDS = 2.8

# Hold progress bar and timer text on the preview
HOLD_BAR_WIDTH = 240          # pixels
HOLD_BAR_HEIGHT = 16          # pixels
HOLD_BAR_BOTTOM_OFFSET = 50   # pixels above the bottom edge
COLOR_HOLD_BAR = (0, 220, 255)     # filling bar (BGR)
COLOR_HOLD_BAR_WAIT = (128, 128, 128)  # grey while waiting for cooldown / release
COLOR_HOLD_BAR_BG = (60, 60, 60)
COLOR_TIMER_TEXT = (0, 255, 0)
COLOR_NOTICE_TEXT = (0, 165, 255)
TIMER_TEXT_MARGIN_RIGHT = 10  # pixels between the timer text and the right edge (top right corner)
NOTICE_Y_OFFSET = 110         # pixels above the bottom edge for the notice text

# ---------------------------------------------------------------------------
# Scroll (Step 6, right hand)
# ---------------------------------------------------------------------------
# Smooth scrolling: every small hand movement scrolls a matching small amount.
# SCROLL_SPEED = wheel units per full frame height of hand movement (Windows: 120
# units = one wheel notch). 9000 = the same speed as before (3 notches per 4% of
# the frame), just in small smooth pieces instead of jumps. Bigger = faster.
SCROLL_SPEED = 9000
SCROLL_DEADZONE = 0.008          # hand movement (fraction of frame height) ignored as jitter
# The scroll direction is remembered across short breaks (e.g. fingertip went
# past the top of the picture). Forgotten after this many seconds without
# pointing, or at once when you make a RIGHT FIST.
SCROLL_DIRECTION_MEMORY_SECONDS = 2.0

# Scroll style:
#   "joystick" (default): where your hand is when you start pointing is the
#       CENTRE. Hold the hand ABOVE it = the page keeps gliding down (like a
#       tablet swipe up), BELOW it = keeps gliding up. Further from the centre =
#       faster (capped). Back to the centre = stop. Reversing is instant.
#   "swipe": like a tablet. A QUICK swipe of the pointing hand flings
#       the page; it keeps gliding and slows down by itself. Slow movements
#       (bringing the hand back) do nothing. Swipe again to go further; swipe the
#       other way to reverse. A right FIST stops the glide (like touching the screen).
#   "drag": the page follows the hand (SCROLL_SPEED, SCROLL_DEADZONE, SCROLL_RATCHET
#       and SCROLL_DIRECTION_MEMORY_SECONDS above apply only to this style).
SCROLL_MODE = "joystick"
SCROLL_JOYSTICK_DEADZONE = 0.04     # fraction of frame height around the centre where nothing happens
SCROLL_JOYSTICK_SPEED = 6000        # wheel units per second for each frame height beyond the dead
                                    # zone (0.1 past it = 600 units/s = 5 notches/s, a gentle glide)
SCROLL_JOYSTICK_MAX_SPEED = 2400    # never faster than this (wheel units per second = 20 notches/s)
COLOR_SCROLL_CENTRE = (255, 128, 255)   # centre band drawn on the preview while scrolling (BGR)
SWIPE_WINDOW_SECONDS = 0.3       # a swipe is a movement that happens within this time...
SWIPE_MIN_DISTANCE = 0.08        # ...and covers at least this fraction of the frame height
SWIPE_GAIN = 2000                # fling speed (wheel units/s) per (frame heights/s) of hand speed
SWIPE_MAX_VELOCITY = 8000        # fastest glide, wheel units per second
SWIPE_DECAY_SECONDS = 0.5        # how quickly the glide slows down (bigger = longer glide)
SWIPE_STOP_VELOCITY = 60         # glide stops when slower than this (wheel units/s)
SWIPE_RETURN_IGNORE_SECONDS = 0.8   # after a swipe, the opposite direction is ignored this long
                                    # (so bringing the hand back doesn't swipe back)
WHEEL_DELTA = 120                # Windows counts one wheel notch as 120 units (fixed by Windows)
SCROLL_TRACK_LANDMARK = 9        # hand point to follow (9 = base of middle finger, steadier than the tip)

# Scroll direction.
#   SCROLL_INVERT = False  -> TOUCHSCREEN style (default): finger moves UP, the page
#                             content moves up, so you travel DOWN the page.
#                             Finger moves DOWN -> you travel UP the page.
#   SCROLL_INVERT = True   -> MOUSE-WHEEL style: finger UP -> you go UP the page,
#                             finger DOWN -> you go DOWN the page.
SCROLL_INVERT = False
COLOR_ACTIVE_TEXT = (255, 128, 255)   # "Active: <gesture>" indicator on the preview (BGR)
ACTIVITY_TEXT_Y_OFFSET = 36           # pixels below the timer line (top right)

# ---------------------------------------------------------------------------
# Zoom (Step 7, right hand)
# ---------------------------------------------------------------------------
# Zoom starts from a NEAR-PINCH (thumb tip almost touching index tip: see
# PINCH_START_DISTANCE above). Then, in "hand sizes" (wrist to middle knuckle):
#   thumb-index distance grows by ZOOM_DISTANCE_STEP  -> one Ctrl+scroll notch ZOOM IN
#   thumb-index distance shrinks by ZOOM_DISTANCE_STEP -> one Ctrl+scroll notch ZOOM OUT
ZOOM_DISTANCE_STEP = 0.20       # tuned: 0.15 zoomed too much for a small movement
ZOOM_DEADZONE = 0.03             # distance changes smaller than this are ignored (in hand sizes)
ZOOM_NOTCHES_PER_STEP = 1        # Ctrl+scroll notches sent per step

# Zoom can ALSO start from a SPREAD pose (thumb and index apart, other three
# fingers curled, thumb not folded), so you can zoom OUT like on a phone:
# start spread, then close to a pinch. (The plan only allowed starting from the
# near-pinch, which made zoom-out impossible without zooming in first.)
ZOOM_START_FROM_SPREAD = True

# How zoom reacts to the thumb-index distance:
#   "joystick" (default): the distance when zoom starts is the CENTRE. Wider than
#       the centre = keeps zooming IN, narrower = keeps zooming OUT, near the
#       centre = stop. Further from the centre = faster. Never runs out of room.
#       Start from the C shape to be able to go both ways.
#   "ratchet": pinch-start = zoom in only, C-start = zoom out only; moving back
#       is a re-grip. Switch by opening the hand briefly.
#   "both": one notch per ZOOM_DISTANCE_STEP of change, spread = in, close = out.
ZOOM_MODE = "joystick"
ZOOM_JOYSTICK_DEADZONE = 0.12    # hand sizes around the centre where nothing happens
ZOOM_JOYSTICK_SPEED = 8.0        # notches per second for each hand size beyond the dead zone
ZOOM_JOYSTICK_MAX_RATE = 6.0     # never more than this many notches per second
ZOOM_SPREAD_START_DISTANCE = 0.7   # thumb-index distance (hand sizes) above this = "spread"
                                   # measured: your spread 1.0-1.3, your pinch 0.08-0.2

# Zoom only ENDS when the thumb is clearly folded: thumb-to-pinky distance below
# this. Lower than THUMB_FOLD_DISTANCE (0.9) on purpose, because during zoom your
# thumb measured 0.93-1.19 and dipped to 0.88: too close to 0.9. Your folded
# pointing thumb is 0.57-0.69, so zoom still can't blend into scroll.
ZOOM_END_THUMB_DISTANCE = 0.75
# RIGHT hand OPEN PALM held HOLD_SECONDS resets zoom to 100% by pressing these keys
# together (Ctrl+0 = "actual size" in browsers, Office, most image viewers).
RESET_ZOOM_KEYS = ("ctrl", "0")
FOCUS_SETTLE_SECONDS = 0.1       # pause after bringing the window under the pointer to the front

# ---------------------------------------------------------------------------
# Screenshot (Step 8, right hand FLAT HAND held HOLD_SECONDS)
# ---------------------------------------------------------------------------
# Saved to <your real Pictures folder>\Screenshots. The real Pictures folder is found
# with the Windows known-folder API, because it may be redirected (e.g. to OneDrive).
SCREENSHOT_FOLDER_NAME = "Screenshots"
SCREENSHOT_FILENAME_FORMAT = "gesture_%Y-%m-%d_%H-%M-%S.png"   # date/time codes, see Python strftime
# The preview window sits on top of the screen, so hide it for a moment while
# the picture is taken (otherwise it would appear in every screenshot).
SCREENSHOT_HIDE_PREVIEW = True
SCREENSHOT_HIDE_DELAY_SECONDS = 0.15    # wait so Windows has really removed the window
MESSAGE_SECONDS = 4.0                   # how long "Screenshot saved" stays on the preview
SCREENSHOT_SAVED_TEXT = "Screenshot saved"
SCREENSHOT_FAILED_TEXT = "Screenshot failed"

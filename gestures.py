"""
gestures.py - everything about understanding hands.

  * HandTracker  - runs MediaPipe on a camera frame and returns the hands found.
  * HandAnalyzer - smooths the hand points, measures things like "is the index
                   finger extended?", and decides which SHAPE the hand is making
                   (POINTING, FIST, OPEN PALM, NEAR-PINCH, FLAT HAND).

Movement tracking (for volume, scroll, zoom) will be added in later steps.
"""

import math
import time
from collections import deque

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

import config

# ---------------------------------------------------------------------------
# MediaPipe's 21 hand landmark numbers (these are fixed by MediaPipe, not tunable)
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8          # MCP = base knuckle, PIP = middle joint
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

# (name, middle joint, tip) for the four long fingers
FINGERS = [
    ("index", INDEX_PIP, INDEX_TIP),
    ("middle", MIDDLE_PIP, MIDDLE_TIP),
    ("ring", RING_PIP, RING_TIP),
    ("pinky", PINKY_PIP, PINKY_TIP),
]

# Shape names shown on screen
POINTING = "POINTING"
POINTING_SIDE = "POINTING SIDE"   # same hand shape, index pointing sideways (either way)
FIST = "FIST"
OPEN_PALM = "OPEN PALM"
NEAR_PINCH = "NEAR-PINCH"
FLAT_HAND = "FLAT HAND"
ZOOM_SPREAD = "ZOOM SPREAD"   # thumb and index apart, others curled (zoom-out start)


class HandTracker:
    """Wraps MediaPipe's HandLandmarker so the rest of the program stays simple."""

    def __init__(self):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=config.MODEL_PATH),
            # VIDEO mode: we feed frames one at a time and get the answer back
            # immediately. MediaPipe uses the previous frame to track faster.
            running_mode=vision.RunningMode.VIDEO,
            num_hands=config.MAX_HANDS,
            min_hand_detection_confidence=config.MIN_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=config.MIN_PRESENCE_CONFIDENCE,
            min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1

    def detect(self, frame_bgr):
        """
        Find hands in one camera frame.

        Returns a list with one dict per hand:
            {
                "label": "Left" or "Right" (after SWAP_HANDEDNESS),
                "mp_label": MediaPipe's original label (before SWAP_HANDEDNESS),
                "score": handedness confidence (0..1),
                "landmarks": list of 21 (x, y, z) tuples,
            }
        x and y are normalized: 0..1 across the frame width/height.
        """
        # OpenCV gives BGR colour order, MediaPipe expects RGB.
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        # VIDEO mode needs a timestamp that always goes up.
        timestamp_ms = int(time.monotonic() * 1000)
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms

        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            category = handedness[0]          # best guess for this hand
            mp_label = category.category_name # "Left" or "Right"
            label = mp_label
            if config.SWAP_HANDEDNESS:
                label = "Right" if label == "Left" else "Left"
            hands.append({
                "label": label,
                "mp_label": mp_label,
                "score": category.score,
                "landmarks": [(lm.x, lm.y, lm.z) for lm in landmarks],
            })
        return hands

    def close(self):
        self._landmarker.close()


# ---------------------------------------------------------------------------
# Small geometry helpers
# ---------------------------------------------------------------------------
def _distance(a, b):
    """Straight-line distance between two points (3D if USE_DEPTH, else 2D)."""
    dx, dy, dz = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    if not config.USE_DEPTH:
        dz = 0.0
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _vector(start, end):
    """Arrow from start to end (3D if USE_DEPTH, else z = 0)."""
    dz = end[2] - start[2] if config.USE_DEPTH else 0.0
    return (end[0] - start[0], end[1] - start[1], dz)


def _angle_between(u, v):
    """Angle in degrees between two arrows (0 = same direction)."""
    dot = sum(a * b for a, b in zip(u, v))
    lengths = math.sqrt(sum(a * a for a in u)) * math.sqrt(sum(b * b for b in v))
    if lengths == 0:
        return 0.0
    # min/max keeps the value in -1..1 so tiny rounding errors can't crash acos
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / lengths))))


def _angle_degrees(start, end):
    """
    Direction from start to end on the screen, in degrees:
    90 = straight up, -90 = straight down, 0 = right, 180 / -180 = left.
    (Screen y grows DOWNWARDS, so we flip it with -dy.)
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    return math.degrees(math.atan2(-dy, dx))


def _is_upright(angle, tolerance):
    """True if the angle is within `tolerance` degrees of straight up (90)."""
    return abs(angle - 90) <= tolerance


def _is_horizontal(angle, tolerance):
    """True if the angle is within `tolerance` degrees of left (180) or right (0)."""
    return abs(angle) <= tolerance or abs(abs(angle) - 180) <= tolerance


class HandAnalyzer:
    """
    Turns raw MediaPipe hands into shapes.

    It remembers a little history per hand ("Left" / "Right"):
      * the smoothed landmark positions (exponential moving average)
      * which shape was seen in the last frames (for SHAPE_STABLE_FRAMES)
    """

    def __init__(self):
        self._smoothed = {}     # label -> list of 21 smoothed (x, y, z)
        self._raw_shape = {}    # label -> shape seen in the last frame
        self._shape_count = {}  # label -> how many frames in a row we've seen it

    def reset(self):
        """Forget all history (e.g. when the camera is turned off)."""
        self._smoothed.clear()
        self._raw_shape.clear()
        self._shape_count.clear()

    def update(self, hands, frame_width, frame_height):
        """
        Analyze this frame's hands. Adds these keys to each hand dict:
            "in_frame":  False if part of the hand is outside the frame margin
            "features":  measurements used for the decision (also shown in debug)
            "points":    smoothed landmarks in 0..1 frame coordinates (or None)
            "raw_shape": shape seen in THIS frame (or None)
            "shape":     shape that has been stable for SHAPE_STABLE_FRAMES (or None)
        Returns the list of hands (at most one per label).
        """
        # If MediaPipe gives two hands the same label (it happens rarely),
        # keep only the more confident one so they don't mix their history.
        best = {}
        for hand in hands:
            if hand["label"] not in best or hand["score"] > best[hand["label"]]["score"]:
                best[hand["label"]] = hand

        # Forget hands that disappeared, so a hand coming back starts fresh.
        for label in list(self._smoothed):
            if label not in best:
                self._forget(label)

        # x and y are fractions of the width and height. The frame is wider
        # than tall, so we rescale y to make one unit the same real size in
        # both directions (otherwise angles and distances would be stretched).
        y_scale = frame_height / frame_width

        for label, hand in best.items():
            hand["in_frame"] = self._fully_in_frame(hand["landmarks"])
            if not hand["in_frame"]:
                # Rule: a hand that is only partly visible never triggers anything.
                self._forget(label)
                hand["features"] = None
                hand["points"] = None
                hand["raw_shape"] = None
                hand["shape"] = None
                continue

            points = [(x, y * y_scale, z) for x, y, z in hand["landmarks"]]
            points = self._smooth(label, points)
            features = self._measure(points, label)
            raw_shape = self._classify(features)

            hand["features"] = features
            # Smoothed points in the same 0..1 frame coordinates as the
            # originals (undo the y rescaling). Used to follow hand movement.
            hand["points"] = [(x, y / y_scale, z) for x, y, z in points]
            hand["raw_shape"] = raw_shape
            hand["shape"] = self._stable_shape(label, raw_shape)

        return list(best.values())

    # ----- history helpers --------------------------------------------------
    def _forget(self, label):
        self._smoothed.pop(label, None)
        self._raw_shape.pop(label, None)
        self._shape_count.pop(label, None)

    @staticmethod
    def _fully_in_frame(landmarks):
        low, high = config.FRAME_MARGIN, 1 - config.FRAME_MARGIN
        return all(low <= x <= high and low <= y <= high for x, y, _ in landmarks)

    def _smooth(self, label, points):
        """
        Exponential moving average: new = alpha * this_frame + (1 - alpha) * old.
        This removes small jitter from MediaPipe.
        """
        old = self._smoothed.get(label)
        if old is None:
            smoothed = points
        else:
            a = config.SMOOTHING_ALPHA
            smoothed = [tuple(a * n + (1 - a) * o for n, o in zip(new_pt, old_pt))
                        for new_pt, old_pt in zip(points, old)]
        self._smoothed[label] = smoothed
        return smoothed

    def _stable_shape(self, label, raw_shape):
        """Return raw_shape only once it has been seen SHAPE_STABLE_FRAMES frames in a row."""
        if label in self._raw_shape and self._raw_shape[label] == raw_shape:
            self._shape_count[label] += 1
        else:
            self._raw_shape[label] = raw_shape
            self._shape_count[label] = 1
        if raw_shape is not None and self._shape_count[label] >= config.SHAPE_STABLE_FRAMES:
            return raw_shape
        return None

    # ----- measuring --------------------------------------------------------
    @staticmethod
    def _measure(p, label):
        """Measure everything the shape rules need. `p` = the 21 smoothed points."""
        wrist = p[WRIST]
        hand_size = max(_distance(wrist, p[MIDDLE_MCP]), 1e-6)   # avoid dividing by 0

        extended = {}
        reach = {}
        for name, pip, tip in FINGERS:
            # Extended: the fingertip is clearly farther from the wrist than the
            # middle joint. Using distances (not just "is the tip higher?") means
            # this also works when the hand is sideways.
            tip_dist = _distance(wrist, p[tip])
            pip_dist = _distance(wrist, p[pip])
            extended[name] = tip_dist > pip_dist * config.FINGER_EXTENDED_RATIO
            # Reach: how far the fingertip is from the wrist, in hand sizes.
            # Small for every finger = a tight fist.
            reach[name] = tip_dist / hand_size

        # Thumb: folded if its tip is close to the PINKY base knuckle. A folded
        # thumb lies across the palm/curled fingers (towards the pinky side);
        # a stretched-out thumb points away from it.
        thumb_dist = _distance(p[THUMB_TIP], p[PINKY_MCP]) / hand_size
        thumb_folded = thumb_dist < config.THUMB_FOLD_DISTANCE

        # Thumb tip to index tip, in hand sizes (small = near-pinch).
        pinch_dist = _distance(p[THUMB_TIP], p[INDEX_TIP]) / hand_size

        # Spread: angle (degrees) between the index finger and the pinky
        # (each measured from its base knuckle to its tip). About 0 when the
        # fingers are held together, 30-50 when spread like a fan.
        spread = _angle_between(_vector(p[INDEX_MCP], p[INDEX_TIP]),
                                _vector(p[PINKY_MCP], p[PINKY_TIP]))

        # Hand direction (wrist -> middle base knuckle) and index direction.
        hand_angle = _angle_degrees(wrist, p[MIDDLE_MCP])
        index_angle = _angle_degrees(p[INDEX_MCP], p[INDEX_TIP])

        # Palm facing the camera? Take the two vectors wrist->index knuckle and
        # wrist->pinky knuckle. The sign of their 2D cross product tells us the
        # order of the knuckles on screen, which flips when the hand turns
        # around. In the mirrored preview, a RIGHT hand with its palm to the
        # camera has the thumb side on the LEFT, which gives a positive sign;
        # a left hand gives a negative sign. (`label` is the corrected label,
        # after SWAP_HANDEDNESS, so it matches your real hand.)
        v1 = (p[INDEX_MCP][0] - wrist[0], p[INDEX_MCP][1] - wrist[1])
        v2 = (p[PINKY_MCP][0] - wrist[0], p[PINKY_MCP][1] - wrist[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        palm_front = (cross > 0) == (label == "Right")
        if not config.MIRROR_FRAME:
            palm_front = not palm_front    # un-mirrored image: everything flips

        # Middle, ring and pinky all curled (needed for zoom, pointing...).
        others_curled = not (extended["middle"] or extended["ring"] or extended["pinky"])

        return {
            "others_curled": others_curled,
            "extended": extended,
            "reach": reach,
            "thumb_dist": thumb_dist,
            "thumb_folded": thumb_folded,
            "pinch_dist": pinch_dist,
            "spread": spread,
            "hand_angle": hand_angle,
            "index_angle": index_angle,
            "palm_front": palm_front,
        }

    # ----- deciding the shape -----------------------------------------------
    @staticmethod
    def _classify(f):
        """
        Decide the shape from the measurements. The ORDER matters: the first
        rule that matches wins, so stricter shapes are checked first.
        """
        ext = f["extended"]
        four_extended = all(ext.values())
        others_curled = not (ext["middle"] or ext["ring"] or ext["pinky"])

        # 1. FIST: every fingertip pulled in close to the wrist, thumb folded.
        #    Checked before NEAR-PINCH because in a fist the thumb tip can also
        #    be near the index tip.
        if all(r < config.FIST_MAX_REACH for r in f["reach"].values()) and f["thumb_folded"]:
            return FIST

        # 2. FLAT HAND: four fingers extended (spread or together) and the hand
        #    points sideways. Palm direction does NOT matter here, because the
        #    camera mostly sees the edge or back of the hand.
        if four_extended and _is_horizontal(f["hand_angle"], config.HORIZONTAL_ANGLE_TOLERANCE):
            return FLAT_HAND

        # 3. OPEN PALM: four fingers extended AND spread, thumb out, hand
        #    upright, palm towards the camera.
        if (four_extended and not f["thumb_folded"]
                and f["spread"] > config.OPEN_PALM_MIN_SPREAD_DEG
                and _is_upright(f["hand_angle"], config.UPRIGHT_ANGLE_TOLERANCE)
                and (f["palm_front"] or not config.REQUIRE_PALM_FACING_CAMERA)):
            return OPEN_PALM

        # 4. NEAR-PINCH: middle/ring/pinky curled and the thumb tip almost
        #    touching the index tip. Only distances are used, so it works even
        #    if the index points sideways or towards the camera.
        if others_curled and f["pinch_dist"] < config.PINCH_START_DISTANCE:
            return NEAR_PINCH

        # 5. POINTING: only the index extended and pointing up, thumb folded
        #    over the curled fingers. (Its thumb is far from the index tip, so
        #    it can't be confused with NEAR-PINCH, which was checked above.)
        if (ext["index"] and others_curled and f["thumb_folded"]
                and _is_upright(f["index_angle"], config.POINTING_ANGLE_TOLERANCE)):
            return POINTING

        # 6. POINTING SIDE: the same hand shape, but the index finger is
        #    horizontal (pointing right OR left) like a slider handle. A second
        #    way to control volume (left hand) and scroll (right hand).
        if (ext["index"] and others_curled and f["thumb_folded"]
                and _is_horizontal(f["index_angle"], config.SIDE_POINTING_ANGLE_TOLERANCE)):
            return POINTING_SIDE

        # 7. ZOOM SPREAD: middle/ring/pinky curled, thumb NOT folded and the
        #    thumb tip far from the index tip (like the letter "C" or "L").
        #    A second way to start zoom, so you can zoom OUT by closing it.
        #    Only distances are used, so the hand may be rotated.
        if (others_curled and not f["thumb_folded"]
                and f["pinch_dist"] > config.ZOOM_SPREAD_START_DISTANCE):
            return ZOOM_SPREAD

        return None


class AnchorStepper:
    """
    Turns smooth up/down hand movement into discrete steps (used for volume,
    and later for scroll).

    How it works:
      * start(y)  remembers where the hand was: the "anchor".
      * Every frame, update(y) compares the hand's height with the anchor.
      * If the hand moved UP by STEP_DISTANCE (a fraction of the frame
        height) we return +1 and move the anchor up by one step. Same for
        DOWN (-1). Otherwise 0.
      * Movement smaller than DEADZONE is ignored completely, so a shaky
        hand doesn't cause steps.
    At most ONE step is returned per frame. If the hand moved fast and is
    still more than a step away from the (moved) anchor, the next frame
    returns the next step, so the response stays smooth.

    RATCHET (ratchet=True): the FIRST step decides the direction for the
    whole gesture. Moving the other way afterwards is a "re-grip": no steps,
    the anchor just follows the hand. So when your hand reaches the top of the
    camera picture you can bring it back down and push up again, without
    leaving the frame. To change direction, end the gesture (change the hand
    shape for a moment) and start again.
    """

    def __init__(self, ratchet=False):
        self._ratchet = ratchet
        self._anchor = None
        self._direction = 0      # ratchet only: 0 = not decided yet, +1 = up, -1 = down

    @property
    def active(self):
        return self._anchor is not None

    def start(self, y):
        self._anchor = y
        self._direction = 0

    def stop(self):
        self._anchor = None
        self._direction = 0

    def update(self, y):
        """Return +1 (moved up a step), -1 (moved down a step) or 0."""
        if self._anchor is None:
            return 0
        # Screen y grows DOWNWARDS, so (anchor - y) is positive when the hand moves up.
        change = self._anchor - y
        if self._ratchet and self._direction != 0 and change * self._direction < 0:
            # Moving the re-grip way: no step, the anchor follows the hand.
            self._anchor = y
            return 0
        if abs(change) < config.DEADZONE or abs(change) < config.STEP_DISTANCE:
            return 0
        direction = 1 if change > 0 else -1
        self._anchor -= direction * config.STEP_DISTANCE   # move anchor one step
        if self._ratchet and self._direction == 0:
            self._direction = direction      # first step fixes the direction
        return direction


class HoldGesture:
    """
    Logic for ONE-TIME gestures (play/pause, timer, screenshot).

    The shape must be held for HOLD_SECONDS without a break. Then the gesture
    "fires" once, and:
      * COOLDOWN_SECONDS must pass before it can fire again, AND
      * the hand must let go of the shape (RELEASE_FRAMES frames in a row
        without it) - so holding a fist doesn't repeat the action.
    If the shape breaks while holding, the hold timer resets to zero.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget everything (used when control turns OFF)."""
        self._hold_start = None       # when the current hold began
        self._cooldown_until = 0.0    # no firing before this time
        self._must_release = False    # True after firing, until the shape is let go
        self._missing_frames = 0      # frames in a row without the shape

    def update(self, active, now):
        """
        Call once per frame. `active` = the right shape is being shown right now.
        Returns (progress, fired):
          progress = 0..1, how far through the hold we are
          fired    = True on the single frame the gesture triggers
        """
        if not active:
            self._hold_start = None           # shape broke: hold timer resets
            self._missing_frames += 1
            if self._missing_frames >= config.RELEASE_FRAMES:
                self._must_release = False    # released long enough: can fire again
            return 0.0, False

        self._missing_frames = 0
        if self._must_release or now < self._cooldown_until:
            self._hold_start = None           # waiting: don't count this hold
            return 0.0, False

        if self._hold_start is None:
            self._hold_start = now
        progress = (now - self._hold_start) / config.HOLD_SECONDS
        if progress >= 1.0:
            self._hold_start = None
            self._cooldown_until = now + config.COOLDOWN_SECONDS
            self._must_release = True
            return 1.0, True
        return progress, False

    def waiting(self, now):
        """True while cooldown or 'release the shape first' blocks this gesture."""
        return self._must_release or now < self._cooldown_until


class ContinuousGesture:
    """
    One continuous gesture (volume, scroll, zoom...): an AnchorStepper plus the
    "release" rule. The gesture only ENDS after RELEASE_FRAMES frames in a row
    without the shape, so a one-frame glitch doesn't cancel it.
    `ratchet=True` makes the first movement fix the direction (see AnchorStepper).
    """

    def __init__(self, ratchet=False):
        self._stepper = AnchorStepper(ratchet)
        self._missing = 0

    @property
    def active(self):
        return self._stepper.active

    def update(self, shape_present, y):
        """
        Call once per frame. `shape_present` = the right shape on the right
        hand is stable now; `y` = hand height (0..1 of the frame, or None).
        Returns (just_started, steps) where steps is +1, -1 or 0.
        """
        if shape_present:
            self._missing = 0
            if not self._stepper.active:
                self._stepper.start(y)       # remember the start height as the anchor
                return True, 0
            return False, self._stepper.update(y)
        if self._stepper.active:
            self._missing += 1
            if self._missing >= config.RELEASE_FRAMES:
                self.stop()
        return False, 0

    def stop(self):
        """End immediately (control turned OFF, camera closed...)."""
        self._stepper.stop()
        self._missing = 0


class ZoomGesture:
    """
    Right-hand zoom.

    START : the NEAR-PINCH shape is stable (thumb tip almost touching index tip,
            middle/ring/pinky curled) - or the ZOOM SPREAD shape, if
            ZOOM_START_FROM_SPREAD is on. The thumb-index distance right then
            is the anchor.
    WHILE : zoom mode stays on as long as middle, ring and pinky stay curled
            (the shape itself may change: once you spread thumb and index it is
            no longer a "near-pinch", but we are still zooming). Only the
            DISTANCE thumb-tip to index-tip, divided by hand size, is used, so
            it works at any camera distance and with a rotated hand.
    MODES (ZOOM_MODE):
      "joystick": the anchor stays fixed as the CENTRE. The further the
            distance is from it (beyond ZOOM_JOYSTICK_DEADZONE), the faster we
            keep sending notches: wider = zoom in, narrower = zoom out. Holding
            the fingers still away from the centre keeps zooming, so you never
            run out of room; going back to the centre stops.
      "both": each time the distance moves ZOOM_DISTANCE_STEP away from the
            anchor we return +1 (fingers spread = zoom in) or -1 (fingers
            closer = zoom out) and move the anchor by one step.
      "ratchet": like "both", but the START shape fixes the direction for the
            whole session, like re-gripping a ratchet spanner:
              started from NEAR-PINCH  -> zoom IN only. Closing the fingers
                                          again does nothing (re-grip), so you
                                          can pinch-spread, pinch-spread...
              started from ZOOM SPREAD -> zoom OUT only. Opening again does
                                          nothing, so you can close, open, close...
            While moving the "re-grip" way the anchor simply follows the
            fingers, so the next real movement counts from where they are now.
            To change direction, end the session (e.g. straighten the middle
            finger for a moment) and start with the other shape.
    END   : middle/ring/pinky extend, the thumb clearly folds over the fingers
            (pointing / fist pose, ZOOM_END_THUMB_DISTANCE), or the hand leaves
            the frame - each for RELEASE_FRAMES frames in a row.
    """

    def __init__(self):
        self._anchor = None
        self._direction = 0      # ratchet: +1 = zoom in only, -1 = zoom out only
        self._missing = 0
        self._last_time = 0.0    # joystick: time of the previous frame
        self._carry = 0.0        # joystick: fraction of a notch saved up so far

    @property
    def active(self):
        return self._anchor is not None

    def update(self, start_shape, features, now):
        """
        Call once per frame.
          start_shape: NEAR_PINCH or ZOOM_SPREAD when that stable shape may start
                       zoom now, otherwise None.
          features:    the hand's measurements (hand["features"]), or None if the
                       hand is missing or partly outside the frame.
          now:         current time in seconds (joystick speed depends on time)
        Returns (just_started, steps) with steps = +1, -1 or 0.
        """
        if self._anchor is None:
            if start_shape in (NEAR_PINCH, ZOOM_SPREAD) and features is not None:
                self._anchor = features["pinch_dist"]
                # Ratchet: pinched fingers can only open (zoom in); spread fingers only close (zoom out).
                self._direction = 1 if start_shape == NEAR_PINCH else -1
                self._missing = 0
                self._last_time = now
                self._carry = 0.0
                return True, 0
            return False, 0

        dt = now - self._last_time
        self._last_time = now

        # Zoom mode is on. Is the hand still in a zoom pose?
        if not self.in_zoom_pose(features):
            self._missing += 1
            if self._missing >= config.RELEASE_FRAMES:
                self.stop()
            return False, 0
        self._missing = 0

        distance = features["pinch_dist"]
        change = distance - self._anchor

        if config.ZOOM_MODE == "joystick":
            # How far past the dead zone around the centre are the fingers?
            excess = abs(change) - config.ZOOM_JOYSTICK_DEADZONE
            if excess <= 0:
                self._carry = 0.0                 # back at the centre: stop
                return False, 0
            rate = min(config.ZOOM_JOYSTICK_MAX_RATE, excess * config.ZOOM_JOYSTICK_SPEED)
            direction = 1 if change > 0 else -1   # wider = zoom in
            self._carry += direction * rate * dt  # notches earned during this frame
            if abs(self._carry) >= 1.0:
                self._carry -= direction          # send one notch, keep the rest
                return False, direction
            return False, 0

        if config.ZOOM_MODE == "ratchet" and change * self._direction < 0:
            # Moving the re-grip way: no zoom, the anchor just follows the fingers.
            self._anchor = distance
            return False, 0
        if abs(change) < config.ZOOM_DEADZONE or abs(change) < config.ZOOM_DISTANCE_STEP:
            return False, 0
        direction = 1 if change > 0 else -1       # fingers apart = +1 = zoom in
        self._anchor += direction * config.ZOOM_DISTANCE_STEP
        return False, direction

    @staticmethod
    def in_zoom_pose(features):
        """True while the hand keeps a zoom pose: middle/ring/pinky curled, thumb not clearly folded."""
        return (features is not None
                and features["others_curled"]
                and features["thumb_dist"] >= config.ZOOM_END_THUMB_DISTANCE)

    def stop(self):
        """End immediately (control turned OFF, camera closed...)."""
        self._anchor = None
        self._direction = 0
        self._missing = 0


class GestureLock:
    """
    ONE GESTURE AT A TIME (safety rule 4).

    Every frame each gesture says whether its shape is present (a dict
    {gesture name: True/False}). The first gesture that becomes present takes
    the lock and becomes the "owner". While it owns the lock, every other
    gesture - on either hand - is ignored. The owner lets go only after its
    shape has been missing for RELEASE_FRAMES frames in a row (shape changed
    or hand left the frame). If several gestures appear on the very same frame,
    the one listed first in the dict wins.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.owner = None        # name of the gesture that has control, or None
        self._missing = 0        # frames in a row the owner's shape was missing

    def update(self, present):
        """Update with this frame's {name: present} dict and return the owner (or None)."""
        if self.owner is not None:
            if present.get(self.owner):
                self._missing = 0
            else:
                self._missing += 1
                if self._missing >= config.RELEASE_FRAMES:
                    self.reset()          # released: anyone may take the lock now
        if self.owner is None:
            for name, is_present in present.items():
                if is_present:
                    self.owner = name
                    self._missing = 0
                    break
        return self.owner


class ScrollGesture:
    """
    Smooth ("glide") scrolling for the right hand, like a touchpad.

    Instead of waiting for a big step and then jumping, every small hand
    movement becomes a matching small scroll:
        scroll amount = hand movement (fraction of frame height) x SCROLL_SPEED
    Movement smaller than SCROLL_DEADZONE is ignored, so a still hand doesn't drift.

    RATCHET (SCROLL_RATCHET = True): the first real movement fixes the
    direction. Moving back the other way is a "re-grip": nothing is scrolled,
    the anchor just follows the hand.

    DIRECTION MEMORY: the direction is remembered even if the gesture ends
    for a moment (e.g. your fingertip went past the top of the camera picture
    and the hand counted as "partly outside"). It is forgotten only when you
    make a FIST with this hand, or after SCROLL_DIRECTION_MEMORY_SECONDS
    without pointing. That way coming back down after hitting the top is
    always a re-grip, never a scroll the wrong way.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Forget everything, including the remembered direction (control OFF)."""
        self.stop()
        self._direction = 0              # 0 = not decided, +1 = finger up, -1 = finger down
        self._last_pointing = float("-inf")

    def stop(self):
        """End the current gesture but keep the remembered direction."""
        self._anchor = None
        self._missing = 0
        self._carry = 0.0                # leftover fraction of a wheel unit

    @property
    def active(self):
        return self._anchor is not None

    def update(self, shape_present, y, fist_seen, now):
        """
        Call once per frame.
          shape_present: pointing shape on this hand (and allowed by the lock)
          y:             hand height 0..1 (None if not present)
          fist_seen:     this hand shows a FIST = "forget the direction"
          now:           current time in seconds
        Returns (just_started, wheel_units): wheel_units > 0 = finger moved UP.
        """
        if fist_seen:
            self._direction = 0          # explicit "I want to reverse"

        if self._anchor is None:
            if shape_present:
                if now - self._last_pointing > config.SCROLL_DIRECTION_MEMORY_SECONDS:
                    self._direction = 0  # long pause: start fresh
                self._anchor = y
                self._missing = 0
                self._carry = 0.0
                self._last_pointing = now
                return True, 0
            return False, 0

        if not shape_present:
            self._missing += 1
            if self._missing >= config.RELEASE_FRAMES:
                self.stop()
            return False, 0
        self._missing = 0
        self._last_pointing = now

        # Screen y grows DOWNWARDS, so (anchor - y) is positive when the hand moves up.
        change = self._anchor - y
        if config.SCROLL_RATCHET and self._direction and change * self._direction < 0:
            self._anchor = y             # re-grip: follow the hand, scroll nothing
            return False, 0
        if abs(change) < config.SCROLL_DEADZONE:
            return False, 0
        self._anchor = y
        if config.SCROLL_RATCHET and not self._direction:
            self._direction = 1 if change > 0 else -1   # first real movement fixes it
        self._carry += change * config.SCROLL_SPEED
        units = int(self._carry)         # whole wheel units only; keep the rest for later
        self._carry -= units
        return False, units


class SwipeScroll:
    """
    Tablet-style scrolling for the right hand: SWIPE to fling the page.

    * A swipe = the pointing hand moves at least SWIPE_MIN_DISTANCE (fraction of
      the frame height) within SWIPE_WINDOW_SECONDS. Slower movements, like
      bringing the hand back for the next swipe, do nothing.
    * A swipe gives the page a speed ("momentum"): faster swipe = faster fling.
      The page keeps gliding even after you stop, slowing down smoothly
      (SWIPE_DECAY_SECONDS) until it stops.
    * Another swipe the same way adds to the glide. A swipe the other way
      reverses it - but for SWIPE_RETURN_IGNORE_SECONDS after a swipe the
      opposite direction is ignored, so your return movement can't fling back.
    * A FIST stops the glide at once (like touching a tablet screen).
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Stop everything (control OFF)."""
        self._samples = deque()          # recent (time, hand height) while pointing
        self._velocity = 0.0             # glide speed in wheel units per second (+ = finger up)
        self._carry = 0.0                # leftover fraction of a wheel unit
        self._last_now = None
        self._blocked_direction = 0      # direction ignored right after a swipe
        self._blocked_until = float("-inf")
        self._pointing = False

    @property
    def active(self):
        """True while the hand is pointing (the glide may continue afterwards)."""
        return self._pointing

    def update(self, shape_present, y, fist_seen, now):
        """
        Call once per frame (even when not pointing, so the glide continues).
        Returns (just_started, wheel_units): wheel_units > 0 = finger moved UP.
        """
        dt = 0.0 if self._last_now is None else now - self._last_now
        self._last_now = now
        just_started = shape_present and not self._pointing
        self._pointing = shape_present

        if fist_seen:
            self._velocity = 0.0             # "touch the screen": stop gliding

        if shape_present:
            self._samples.append((now, y))
            # keep only the last SWIPE_WINDOW_SECONDS of movement
            while now - self._samples[0][0] > config.SWIPE_WINDOW_SECONDS:
                self._samples.popleft()
            start_time, start_y = self._samples[0]
            moved = start_y - y              # screen y grows downwards: + = hand moved up
            if abs(moved) >= config.SWIPE_MIN_DISTANCE and now > start_time:
                direction = 1 if moved > 0 else -1
                blocked = direction == self._blocked_direction and now < self._blocked_until
                if not blocked:
                    hand_speed = abs(moved) / (now - start_time)       # frame heights per second
                    fling = direction * min(config.SWIPE_MAX_VELOCITY,
                                            hand_speed * config.SWIPE_GAIN)
                    if self._velocity * direction > 0:                 # same way: add to the glide
                        self._velocity += fling
                        self._velocity = max(-config.SWIPE_MAX_VELOCITY,
                                             min(config.SWIPE_MAX_VELOCITY, self._velocity))
                    else:                                              # other way (or still): replace
                        self._velocity = fling
                    self._blocked_direction = -direction
                    self._blocked_until = now + config.SWIPE_RETURN_IGNORE_SECONDS
                # This stroke has been used (or ignored): start measuring afresh.
                self._samples.clear()
                self._samples.append((now, y))
        else:
            self._samples.clear()

        # Glide: move by speed x time, then slow down smoothly.
        units = 0
        if self._velocity and dt > 0:
            self._carry += self._velocity * dt
            self._velocity *= math.exp(-dt / config.SWIPE_DECAY_SECONDS)
            if abs(self._velocity) < config.SWIPE_STOP_VELOCITY:
                self._velocity = 0.0
            units = int(self._carry)         # whole wheel units only; keep the rest
            self._carry -= units
        return just_started, units


class JoystickScroll:
    """
    Joystick scrolling for the right hand (rate control, like the zoom joystick).

    When you start pointing, the hand height is the CENTRE. After that the
    page keeps scrolling while the hand is away from the centre:
        speed = (distance from centre - SCROLL_JOYSTICK_DEADZONE) x SCROLL_JOYSTICK_SPEED
    capped at SCROLL_JOYSTICK_MAX_SPEED. Above the centre = finger "up" (the
    page travels down, touchscreen style), below = finger "down". Inside the
    dead zone nothing happens, so you stop by going back to the centre.
    Because it is speed, not position, you never run out of room in the
    camera picture.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Stop everything (control OFF)."""
        self._centre = None
        self._missing = 0
        self._carry = 0.0                # leftover fraction of a wheel unit
        self._last_now = None

    @property
    def active(self):
        return self._centre is not None

    @property
    def centre(self):
        """Centre height (0..1 of the frame) while active, else None (for drawing)."""
        return self._centre

    def update(self, shape_present, y, fist_seen, now):
        """
        Call once per frame. (fist_seen is not needed here: going back to the
        centre already stops. It is accepted so all scroll styles look alike.)
        Returns (just_started, wheel_units): wheel_units > 0 = finger moved UP.
        """
        dt = 0.0 if self._last_now is None else now - self._last_now
        self._last_now = now

        if self._centre is None:
            if shape_present:
                self._centre = y         # this height is the "stop" position
                self._missing = 0
                self._carry = 0.0
                return True, 0
            return False, 0

        if not shape_present:
            # Hand lost for a moment: don't scroll; end after RELEASE_FRAMES.
            self._missing += 1
            if self._missing >= config.RELEASE_FRAMES:
                self.reset()
                self._last_now = now
            return False, 0
        self._missing = 0

        offset = self._centre - y        # screen y grows downwards: + = hand above the centre
        excess = abs(offset) - config.SCROLL_JOYSTICK_DEADZONE
        if excess <= 0:
            self._carry = 0.0            # inside the dead zone: stop
            return False, 0
        speed = min(config.SCROLL_JOYSTICK_MAX_SPEED, excess * config.SCROLL_JOYSTICK_SPEED)
        direction = 1 if offset > 0 else -1
        self._carry += direction * speed * dt
        units = int(self._carry)         # whole wheel units only; keep the rest
        self._carry -= units
        return False, units

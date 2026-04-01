# MK3 Overlay Widget System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Python/Qt overlay daemon that renders interactive widgets on the MK3 screens, with the settings menu as the first widget.

**Architecture:** A single Python daemon reads HID from the MK3 via hidraw, manages widget lifecycle, renders frameless Qt windows on Xvfb :99 (captured by the screen daemon), and coordinates with Mixxx JS and other daemons via xdotool keystrokes and flag files.

**Tech Stack:** Python 3, PyQt5, hidraw (raw OS file I/O), xdotool, systemd

---

## File Structure

```
pi-setup/
  mk3_overlay/                 # underscore — valid Python package name
    __init__.py              # Package marker (empty)
    daemon.py                # Entry point: QApplication, QTimer HID poll, widget manager
    hid.py                   # hidraw discovery, non-blocking read, report parsing, LED writing
    widget.py                # Widget/Page/Item base classes and dataclasses
    renderer.py              # OverlayWindow (QWidget), QPainter page/item rendering
    focus.py                 # Flag file + xdotool signaling for focus trap
    widgets/
      __init__.py            # Package marker (empty)
      settings.py            # Settings widget: 3 pages, system commands, info queries
  mk3-overlay.service        # systemd unit (hyphen ok — not Python)
  tests/
    test_widget.py           # Widget/Page/Item navigation logic tests
    test_hid.py              # HID report parsing tests
    test_settings.py         # Settings widget action/toggle/info tests
```

Modified existing files:
- `pi-setup/mk3-t9-daemon.py` — add overlay-active flag check
- `pi-setup/mk3-mouse-daemon.py` — add overlay-active flag check
- `mapping/Native-Instruments-Maschine-MK3.js` — remove settings code, add overlay F-key handlers
- `skin/MK3/skin.xml` — remove SettingsPanel and settings COs
- `skin/MK3/style.qss` — remove Settings styles

---

### Task 1: HID report parsing and device discovery (`hid.py`)

**Files:**
- Create: `pi-setup/mk3_overlay/hid.py`
- Create: `pi-setup/tests/test_hid.py`
- Create: `pi-setup/mk3_overlay/__init__.py`

This module handles hidraw discovery, non-blocking reads, button/knob/stepper parsing from Report 0x01, and LED report writing. Accepts an optional device path override for future emulator support.

- [ ] **Step 1: Write failing tests for HID report parsing**

Create `pi-setup/tests/test_hid.py`:

```python
"""Tests for HID report parsing."""
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mk3_overlay.hid import parse_buttons, parse_knob, parse_stepper, BUTTONS


class TestParseButtons(unittest.TestCase):
    """Test button edge detection from Report 0x01."""

    def _make_report(self, overrides=None):
        """Build a 12-byte Report 0x01 with optional byte overrides."""
        data = bytearray(12)
        data[0] = 0x01
        if overrides:
            for idx, val in overrides.items():
                data[idx] = val
        return bytes(data)

    def test_no_buttons_pressed(self):
        report = self._make_report()
        prev = self._make_report()
        pressed, released = parse_buttons(report, prev)
        self.assertEqual(pressed, set())
        self.assertEqual(released, set())

    def test_single_button_press(self):
        # settings button: byte 0x07, mask 0x02
        prev = self._make_report()
        curr = self._make_report({0x07: 0x02})
        pressed, released = parse_buttons(curr, prev)
        self.assertIn("settings", pressed)
        self.assertEqual(released, set())

    def test_single_button_release(self):
        prev = self._make_report({0x07: 0x02})
        curr = self._make_report()
        pressed, released = parse_buttons(curr, prev)
        self.assertEqual(pressed, set())
        self.assertIn("settings", released)

    def test_held_button_no_edge(self):
        both = self._make_report({0x07: 0x02})
        pressed, released = parse_buttons(both, both)
        self.assertEqual(pressed, set())
        self.assertEqual(released, set())

    def test_multiple_buttons(self):
        prev = self._make_report()
        curr = self._make_report({0x01: 0x05})  # navPush (0x01) + navUp (0x04)
        pressed, released = parse_buttons(curr, prev)
        self.assertIn("navPush", pressed)
        self.assertIn("navUp", pressed)


class TestParseKnob(unittest.TestCase):
    """Test 16-bit knob delta extraction."""

    def test_knob_clockwise(self):
        prev_report = bytearray(28)
        prev_report[0] = 0x01
        prev_report[12] = 0x00  # k1 LSB
        prev_report[13] = 0x00  # k1 MSB

        curr_report = bytearray(28)
        curr_report[0] = 0x01
        curr_report[12] = 0x05  # k1 LSB
        curr_report[13] = 0x00  # k1 MSB

        delta = parse_knob(bytes(curr_report), bytes(prev_report), "k1")
        self.assertEqual(delta, 5)

    def test_knob_counter_clockwise(self):
        prev_report = bytearray(28)
        prev_report[0] = 0x01
        prev_report[12] = 0x05
        prev_report[13] = 0x00

        curr_report = bytearray(28)
        curr_report[0] = 0x01
        curr_report[12] = 0x00
        curr_report[13] = 0x00

        delta = parse_knob(bytes(curr_report), bytes(prev_report), "k1")
        self.assertEqual(delta, -5)

    def test_knob_no_change(self):
        report = bytearray(28)
        report[0] = 0x01
        delta = parse_knob(bytes(report), bytes(report), "k1")
        self.assertEqual(delta, 0)


class TestParseStepper(unittest.TestCase):
    """Test stepper (nav wheel) delta extraction."""

    def test_stepper_clockwise(self):
        prev = bytearray(12)
        prev[0] = 0x01
        prev[11] = 0x03  # lower nibble = position

        curr = bytearray(12)
        curr[0] = 0x01
        curr[11] = 0x05

        delta = parse_stepper(bytes(curr), bytes(prev))
        self.assertEqual(delta, 1)  # positive = clockwise

    def test_stepper_counter_clockwise(self):
        prev = bytearray(12)
        prev[0] = 0x01
        prev[11] = 0x05

        curr = bytearray(12)
        curr[0] = 0x01
        curr[11] = 0x03

        delta = parse_stepper(bytes(curr), bytes(prev))
        self.assertEqual(delta, -1)

    def test_stepper_no_change(self):
        report = bytearray(12)
        report[0] = 0x01
        report[11] = 0x05
        delta = parse_stepper(bytes(report), bytes(report))
        self.assertEqual(delta, 0)

    def test_stepper_wraparound_forward(self):
        prev = bytearray(12)
        prev[0] = 0x01
        prev[11] = 0x0F

        curr = bytearray(12)
        curr[0] = 0x01
        curr[11] = 0x00

        delta = parse_stepper(bytes(curr), bytes(prev))
        self.assertEqual(delta, 1)

    def test_stepper_wraparound_backward(self):
        prev = bytearray(12)
        prev[0] = 0x01
        prev[11] = 0x00

        curr = bytearray(12)
        curr[0] = 0x01
        curr[11] = 0x0F

        delta = parse_stepper(bytes(curr), bytes(prev))
        self.assertEqual(delta, -1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/test_hid.py -v`
Expected: `ModuleNotFoundError: No module named 'mk3_overlay'`

- [ ] **Step 3: Implement hid.py**

Create `pi-setup/mk3_overlay/__init__.py` (empty file).

Create `pi-setup/mk3_overlay/hid.py`:

```python
"""HID device discovery, report parsing, and LED output for the MK3."""
import glob
import os
import fcntl

VENDOR_ID = "17CC"
PRODUCT_ID = "1600"

# Button map: name -> (byte_index, bitmask)
# Byte indices match Report 0x01 layout.
BUTTONS = {
    "navPush":        (0x01, 0x01),
    "navUp":          (0x01, 0x04),
    "navRight":       (0x01, 0x08),
    "navDown":        (0x01, 0x10),
    "navLeft":        (0x01, 0x20),
    "shift":          (0x01, 0x40),
    "d8":             (0x01, 0x80),
    "g1":             (0x02, 0x01),
    "g2":             (0x02, 0x02),
    "g3":             (0x02, 0x04),
    "g4":             (0x02, 0x08),
    "g5":             (0x02, 0x10),
    "g6":             (0x02, 0x20),
    "g7":             (0x02, 0x40),
    "g8":             (0x02, 0x80),
    "notes":          (0x03, 0x01),
    "volume":         (0x03, 0x02),
    "swing":          (0x03, 0x04),
    "tempo":          (0x03, 0x08),
    "noteRepeatArp":  (0x03, 0x10),
    "lock":           (0x03, 0x20),
    "padMode":        (0x04, 0x01),
    "keyboard":       (0x04, 0x02),
    "chords":         (0x04, 0x04),
    "step":           (0x04, 0x08),
    "fixedVel":       (0x04, 0x10),
    "scene":          (0x04, 0x20),
    "pattern":        (0x04, 0x40),
    "events":         (0x04, 0x80),
    "variationNavigate": (0x05, 0x02),
    "duplicateDouble":   (0x05, 0x04),
    "select":         (0x05, 0x08),
    "solo":           (0x05, 0x10),
    "muteChoke":      (0x05, 0x20),
    "pitch":          (0x05, 0x40),
    "mod":            (0x05, 0x80),
    "performFxSelect":(0x06, 0x01),
    "restartLoop":    (0x06, 0x02),
    "eraseReplace":   (0x06, 0x04),
    "tapMetro":       (0x06, 0x08),
    "followGrid":     (0x06, 0x10),
    "play":           (0x06, 0x20),
    "recCountIn":     (0x06, 0x40),
    "stop":           (0x06, 0x80),
    "macroSet":       (0x07, 0x01),
    "settings":       (0x07, 0x02),
    "arrowRight":     (0x07, 0x04),
    "sampling":       (0x07, 0x08),
    "mixer":          (0x07, 0x10),
    "plugin":         (0x07, 0x20),
    "channelMidi":    (0x08, 0x01),
    "arranger":       (0x08, 0x02),
    "browserPlugin":  (0x08, 0x04),
    "arrowLeft":      (0x08, 0x08),
    "fileSave":       (0x08, 0x10),
    "auto":           (0x08, 0x20),
    "d1":             (0x09, 0x01),
    "d2":             (0x09, 0x02),
    "d3":             (0x09, 0x04),
    "d4":             (0x09, 0x08),
    "d5":             (0x09, 0x10),
    "d6":             (0x09, 0x20),
    "d7":             (0x09, 0x40),
}

# Knob descriptors: name -> (lsb_addr, msb_addr)
KNOBS = {
    "k1": (12, 13), "k2": (14, 15), "k3": (16, 17), "k4": (18, 19),
    "k5": (20, 21), "k6": (22, 23), "k7": (24, 25), "k8": (26, 27),
}

STEPPER_BYTE = 11

# LED map: name -> (report_id, byte_offset)
LEDS = {
    "settings":    (0x80, 10),
    "d1": (0x80, 13), "d2": (0x80, 14), "d3": (0x80, 15), "d4": (0x80, 16),
    "d5": (0x80, 17), "d6": (0x80, 18), "d7": (0x80, 19), "d8": (0x80, 20),
    "arrowLeft":   (0x80, 7),
    "arrowRight":  (0x80, 8),
}

# LED report buffers
LED_REPORT_80_SIZE = 63
LED_REPORT_81_SIZE = 43


def find_hidraw(device_path=None):
    """Find the hidraw device for the MK3 HID interface.

    If device_path is given, use it directly (for emulator support).
    Otherwise scan /dev/hidraw* by vendor/product ID.
    Returns the path string or None.
    """
    if device_path:
        return device_path
    for hidraw in sorted(glob.glob("/dev/hidraw*")):
        try:
            devnum = hidraw.replace("/dev/hidraw", "")
            uevent = f"/sys/class/hidraw/hidraw{devnum}/device/uevent"
            if os.path.exists(uevent):
                with open(uevent) as f:
                    content = f.read().upper()
                    if VENDOR_ID in content and PRODUCT_ID in content:
                        return hidraw
        except (IOError, OSError):
            continue
    return None


def open_hidraw(path):
    """Open a hidraw device for non-blocking read/write. Returns fd."""
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    return fd


def read_report(fd):
    """Non-blocking read of one HID report. Returns bytes or None."""
    try:
        return os.read(fd, 64)
    except BlockingIOError:
        return None
    except OSError:
        return None


def parse_buttons(curr, prev):
    """Compare two Report 0x01 buffers and return (pressed, released) sets of button names."""
    pressed = set()
    released = set()
    for name, (byte_idx, mask) in BUTTONS.items():
        if byte_idx >= len(curr) or byte_idx >= len(prev):
            continue
        is_on = (curr[byte_idx] & mask) != 0
        was_on = (prev[byte_idx] & mask) != 0
        if is_on and not was_on:
            pressed.add(name)
        elif was_on and not is_on:
            released.add(name)
    return pressed, released


def parse_knob(curr, prev, knob_name):
    """Extract signed delta for a 16-bit knob between two reports.

    Handles wraparound at 65536 boundary with ±2048 threshold.
    """
    lsb, msb = KNOBS[knob_name]
    if msb >= len(curr) or msb >= len(prev):
        return 0
    curr_val = curr[lsb] | (curr[msb] << 8)
    prev_val = prev[lsb] | (prev[msb] << 8)
    delta = curr_val - prev_val
    if delta > 32768:
        delta -= 65536
    elif delta < -32768:
        delta += 65536
    return delta


def parse_stepper(curr, prev):
    """Extract stepper direction from lower nibble of byte 11.

    Returns 1 (clockwise), -1 (counter-clockwise), or 0 (no change).
    """
    if STEPPER_BYTE >= len(curr) or STEPPER_BYTE >= len(prev):
        return 0
    curr_pos = curr[STEPPER_BYTE] & 0x0F
    prev_pos = prev[STEPPER_BYTE] & 0x0F
    if curr_pos == prev_pos:
        return 0
    diff = (curr_pos - prev_pos) & 0x0F
    if diff <= 7:
        return 1
    return -1


class LedWriter:
    """Manages LED report buffers and writes them to hidraw."""

    def __init__(self, fd):
        self._fd = fd
        self._buf80 = bytearray(LED_REPORT_80_SIZE)
        self._buf80[0] = 0x80
        self._buf81 = bytearray(LED_REPORT_81_SIZE)
        self._buf81[0] = 0x81

    def set_led(self, name, value):
        """Set a single LED by name. value is brightness (0-63) or color index (0-71)."""
        if name not in LEDS:
            return
        report_id, offset = LEDS[name]
        if report_id == 0x80:
            self._buf80[offset] = value
        else:
            self._buf81[offset] = value

    def send(self):
        """Write both LED reports to the device."""
        try:
            os.write(self._fd, bytes(self._buf80))
            os.write(self._fd, bytes(self._buf81))
        except OSError:
            pass

    def all_off(self):
        """Zero all LED values (except report IDs)."""
        for i in range(1, LED_REPORT_80_SIZE):
            self._buf80[i] = 0
        for i in range(1, LED_REPORT_81_SIZE):
            self._buf81[i] = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/test_hid.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pi-setup/mk3_overlay/__init__.py pi-setup/mk3_overlay/hid.py pi-setup/tests/test_hid.py
git commit -m "feat(overlay): add HID report parsing and device discovery"
```

---

### Task 2: Widget, Page, and Item data model (`widget.py`)

**Files:**
- Create: `pi-setup/mk3_overlay/widget.py`
- Create: `pi-setup/tests/test_widget.py`

Core navigation logic: cursor movement (skipping info items, wrapping), page switching, confirmation flow, toggle state management. No rendering — pure state.

- [ ] **Step 1: Write failing tests for navigation logic**

Create `pi-setup/tests/test_widget.py`:

```python
"""Tests for Widget/Page/Item navigation logic."""
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mk3_overlay.widget import Widget, Page, ActionItem, ToggleItem, InfoItem


class TestCursorNavigation(unittest.TestCase):
    """Test cursor movement through selectable items."""

    def _make_widget(self):
        page = Page(title="TEST", items=[
            ActionItem(label="Action 1"),
            InfoItem(label="Info (skip)"),
            ActionItem(label="Action 2"),
            ToggleItem(label="Toggle 1", state=False),
        ])
        w = Widget(name="test", position=(0, 0, 480, 272),
                   activate_button="settings", pages=[page])
        return w

    def test_initial_cursor_on_first_selectable(self):
        w = self._make_widget()
        self.assertEqual(w.cursor, 0)

    def test_move_down_skips_info(self):
        w = self._make_widget()
        w.move_cursor(1)
        self.assertEqual(w.cursor, 2)  # skipped index 1 (info)

    def test_move_up_skips_info(self):
        w = self._make_widget()
        w.cursor = 2
        w.move_cursor(-1)
        self.assertEqual(w.cursor, 0)  # skipped index 1 (info)

    def test_wrap_down(self):
        w = self._make_widget()
        w.cursor = 3  # last selectable
        w.move_cursor(1)
        self.assertEqual(w.cursor, 0)  # wrap to first

    def test_wrap_up(self):
        w = self._make_widget()
        w.cursor = 0
        w.move_cursor(-1)
        self.assertEqual(w.cursor, 3)  # wrap to last selectable


class TestPageSwitching(unittest.TestCase):
    """Test page switching with left/right."""

    def _make_widget(self):
        pages = [
            Page(title="P1", items=[ActionItem(label="A")]),
            Page(title="P2", items=[ActionItem(label="B"), InfoItem(label="I"), ActionItem(label="C")]),
            Page(title="P3", items=[InfoItem(label="I"), ToggleItem(label="T", state=True)]),
        ]
        w = Widget(name="test", position=(0, 0, 480, 272),
                   activate_button="settings", pages=pages)
        return w

    def test_initial_page(self):
        w = self._make_widget()
        self.assertEqual(w.current_page, 0)

    def test_next_page(self):
        w = self._make_widget()
        w.switch_page(1)
        self.assertEqual(w.current_page, 1)

    def test_prev_page_wraps(self):
        w = self._make_widget()
        w.switch_page(-1)
        self.assertEqual(w.current_page, 2)

    def test_next_page_wraps(self):
        w = self._make_widget()
        w.current_page = 2
        w.switch_page(1)
        self.assertEqual(w.current_page, 0)

    def test_cursor_resets_to_first_selectable_on_page_switch(self):
        w = self._make_widget()
        w.cursor = 0
        w.switch_page(1)  # page 2 has selectable at 0
        self.assertEqual(w.cursor, 0)
        w.switch_page(1)  # page 3: info at 0, toggle at 1
        self.assertEqual(w.cursor, 1)

    def test_jump_to_page(self):
        w = self._make_widget()
        w.jump_to_page(2)
        self.assertEqual(w.current_page, 2)

    def test_jump_to_page_out_of_range_ignored(self):
        w = self._make_widget()
        w.jump_to_page(5)
        self.assertEqual(w.current_page, 0)  # unchanged


class TestConfirmation(unittest.TestCase):
    """Test two-step confirmation for destructive actions."""

    def test_confirm_action_first_push_enters_confirm(self):
        executed = []
        page = Page(title="T", items=[
            ActionItem(label="Dangerous", confirm=True,
                       on_execute=lambda: executed.append(True)),
        ])
        w = Widget(name="t", position=(0, 0, 480, 272),
                   activate_button="x", pages=[page])
        w.execute_item()
        self.assertTrue(w.confirming)
        self.assertEqual(executed, [])  # not yet executed

    def test_confirm_action_second_push_executes(self):
        executed = []
        page = Page(title="T", items=[
            ActionItem(label="Dangerous", confirm=True,
                       on_execute=lambda: executed.append(True)),
        ])
        w = Widget(name="t", position=(0, 0, 480, 272),
                   activate_button="x", pages=[page])
        w.execute_item()  # enter confirm
        w.execute_item()  # confirm
        self.assertFalse(w.confirming)
        self.assertEqual(executed, [True])

    def test_cursor_move_cancels_confirm(self):
        page = Page(title="T", items=[
            ActionItem(label="A", confirm=True, on_execute=lambda: None),
            ActionItem(label="B"),
        ])
        w = Widget(name="t", position=(0, 0, 480, 272),
                   activate_button="x", pages=[page])
        w.execute_item()
        self.assertTrue(w.confirming)
        w.move_cursor(1)
        self.assertFalse(w.confirming)

    def test_non_confirm_action_executes_immediately(self):
        executed = []
        page = Page(title="T", items=[
            ActionItem(label="Safe", on_execute=lambda: executed.append(True)),
        ])
        w = Widget(name="t", position=(0, 0, 480, 272),
                   activate_button="x", pages=[page])
        w.execute_item()
        self.assertEqual(executed, [True])


class TestToggle(unittest.TestCase):
    """Test toggle items."""

    def test_toggle_flips_state(self):
        toggled = []
        page = Page(title="T", items=[
            ToggleItem(label="Opt", state=False,
                       on_toggle=lambda s: toggled.append(s)),
        ])
        w = Widget(name="t", position=(0, 0, 480, 272),
                   activate_button="x", pages=[page])
        w.execute_item()
        self.assertTrue(w.pages[0].items[0].state)
        self.assertEqual(toggled, [True])

    def test_toggle_flips_back(self):
        toggled = []
        page = Page(title="T", items=[
            ToggleItem(label="Opt", state=True,
                       on_toggle=lambda s: toggled.append(s)),
        ])
        w = Widget(name="t", position=(0, 0, 480, 272),
                   activate_button="x", pages=[page])
        w.execute_item()
        self.assertFalse(w.pages[0].items[0].state)
        self.assertEqual(toggled, [False])


class TestInfoItem(unittest.TestCase):
    """Test info items are skipped and display values."""

    def test_info_value_fn(self):
        item = InfoItem(label="IP", value_fn=lambda: "192.168.1.5")
        self.assertEqual(item.get_value(), "192.168.1.5")

    def test_info_no_value_fn(self):
        item = InfoItem(label="Version")
        self.assertEqual(item.get_value(), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/test_widget.py -v`
Expected: `ImportError: cannot import name 'Widget' from 'mk3_overlay.widget'`

- [ ] **Step 3: Implement widget.py**

Create `pi-setup/mk3_overlay/widget.py`:

```python
"""Widget, Page, and Item base classes for the MK3 overlay system."""


class ActionItem:
    """A menu item that executes a callback. Optionally requires confirmation."""

    def __init__(self, label, on_execute=None, confirm=False):
        self.label = label
        self.on_execute = on_execute
        self.confirm = confirm
        self.selectable = True


class ToggleItem:
    """A menu item with an on/off state."""

    def __init__(self, label, state=False, on_toggle=None):
        self.label = label
        self.state = state
        self.on_toggle = on_toggle
        self.selectable = True


class InfoItem:
    """A read-only display item. Cursor skips over it."""

    def __init__(self, label, value_fn=None):
        self.label = label
        self.value_fn = value_fn
        self.selectable = False

    def get_value(self):
        if self.value_fn:
            return self.value_fn()
        return ""


class Page:
    """A single page within a widget. Contains items and optional hardware bindings."""

    def __init__(self, title, items=None, knob_bindings=None, d_button_bindings=None):
        self.title = title
        self.items = items or []
        self.knob_bindings = knob_bindings or {}
        self.d_button_bindings = d_button_bindings or {}

    def first_selectable(self):
        """Return the index of the first selectable item, or 0."""
        for i, item in enumerate(self.items):
            if item.selectable:
                return i
        return 0

    def next_selectable(self, current, direction):
        """Return the next selectable index, wrapping around. Skips info items."""
        n = len(self.items)
        if n == 0:
            return 0
        idx = current
        for _ in range(n):
            idx = (idx + direction) % n
            if self.items[idx].selectable:
                return idx
        return current


class Widget:
    """Base class for an overlay widget.

    Manages pages, cursor position, confirmation state, and
    provides the navigation/execution interface that the daemon calls.
    """

    def __init__(self, name, position, activate_button, pages):
        self.name = name
        self.position = position  # (x, y, w, h)
        self.activate_button = activate_button
        self.pages = pages
        self.current_page = 0
        self.cursor = self.pages[0].first_selectable() if pages else 0
        self.confirming = False
        self._confirm_timer = None

    @property
    def page(self):
        """The currently active page."""
        return self.pages[self.current_page]

    def move_cursor(self, direction):
        """Move cursor up (-1) or down (+1), skipping non-selectable items."""
        self.confirming = False
        self.cursor = self.page.next_selectable(self.cursor, direction)

    def switch_page(self, direction):
        """Switch to next (+1) or previous (-1) page, wrapping."""
        self.confirming = False
        self.current_page = (self.current_page + direction) % len(self.pages)
        self.cursor = self.page.first_selectable()
        self.on_page_enter()

    def jump_to_page(self, index):
        """Jump directly to a page by index. Ignored if out of range."""
        if 0 <= index < len(self.pages):
            self.confirming = False
            self.current_page = index
            self.cursor = self.page.first_selectable()
            self.on_page_enter()

    def execute_item(self):
        """Execute the currently highlighted item."""
        items = self.page.items
        if self.cursor >= len(items):
            return
        item = items[self.cursor]

        if isinstance(item, ToggleItem):
            item.state = not item.state
            if item.on_toggle:
                item.on_toggle(item.state)
            return

        if isinstance(item, ActionItem):
            if item.confirm and not self.confirming:
                self.confirming = True
                return
            self.confirming = False
            if item.on_execute:
                item.on_execute()
            return

    def cancel_confirm(self):
        """Cancel any pending confirmation."""
        self.confirming = False

    def on_page_enter(self):
        """Called when switching to a page. Override for info refresh."""
        pass

    def on_activate(self):
        """Called when the widget is shown. Override for setup."""
        self.current_page = 0
        self.cursor = self.page.first_selectable()
        self.confirming = False
        self.on_page_enter()

    def on_deactivate(self):
        """Called when the widget is hidden. Override for cleanup."""
        self.confirming = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/test_widget.py -v`
Expected: All 17 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pi-setup/mk3_overlay/widget.py pi-setup/tests/test_widget.py
git commit -m "feat(overlay): add Widget/Page/Item data model with navigation logic"
```

---

### Task 3: Focus trap (`focus.py`)

**Files:**
- Create: `pi-setup/mk3_overlay/focus.py`

Manages the `/tmp/mk3-overlay-active` flag file and sends xdotool keystrokes to notify Mixxx JS.

- [ ] **Step 1: Implement focus.py**

Create `pi-setup/mk3_overlay/focus.py`:

```python
"""Focus trap: flag file and xdotool signaling for overlay activation."""
import os
import subprocess

FLAG_FILE = "/tmp/mk3-overlay-active"
DISPLAY = os.environ.get("DISPLAY", ":99")


def activate(display=None):
    """Signal that an overlay widget has taken focus.

    Writes the flag file and sends F12 to Mixxx via xdotool.
    """
    _display = display or DISPLAY
    try:
        with open(FLAG_FILE, "w") as f:
            f.write("1\n")
    except IOError:
        pass
    _send_key("F12", _display)


def deactivate(display=None):
    """Signal that the overlay widget has released focus.

    Removes the flag file and sends F11 to Mixxx via xdotool.
    """
    _display = display or DISPLAY
    try:
        os.remove(FLAG_FILE)
    except OSError:
        pass
    _send_key("F11", _display)


def send_rescan(display=None):
    """Send F10 to Mixxx to trigger library rescan."""
    _display = display or DISPLAY
    _send_key("F10", _display)


def is_active():
    """Check if the overlay flag file exists."""
    return os.path.exists(FLAG_FILE)


def _send_key(key, display):
    """Send a keystroke via xdotool."""
    try:
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", key],
            env={**os.environ, "DISPLAY": display},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
```

- [ ] **Step 2: Commit**

```bash
git add pi-setup/mk3_overlay/focus.py
git commit -m "feat(overlay): add focus trap with flag file and xdotool signaling"
```

---

### Task 4: Qt renderer (`renderer.py`)

**Files:**
- Create: `pi-setup/mk3_overlay/renderer.py`

The `OverlayWindow` QWidget subclass: frameless window, QPainter rendering of the standard page layout (tab bar, item list, confirmation state).

- [ ] **Step 1: Implement renderer.py**

Create `pi-setup/mk3_overlay/renderer.py`:

```python
"""Qt overlay window and QPainter rendering for the MK3 widget system."""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QColor, QFont, QPen

from .widget import ActionItem, ToggleItem, InfoItem

# Color palette (matches MK3 skin aesthetic)
BG = QColor(0x0d, 0x0d, 0x1a)
TAB_BAR_BG = QColor(0x11, 0x11, 0x22)
TAB_ACTIVE = QColor(0xe6, 0x7e, 0x22)
TAB_INACTIVE = QColor(0x55, 0x55, 0x55)
ITEM_TEXT = QColor(0xaa, 0xaa, 0xaa)
ITEM_TEXT_HL = QColor(0xff, 0xff, 0xff)
ITEM_BG_HL = QColor(0x1a, 0x1a, 0x2e)
ACCENT = QColor(0xe6, 0x7e, 0x22)
INFO_TEXT = QColor(0x55, 0x55, 0x55)
TOGGLE_ON_BG = QColor(0xe6, 0x7e, 0x22)
TOGGLE_OFF_BG = QColor(0x33, 0x33, 0x33)
TOGGLE_ON_TEXT = QColor(0xff, 0xff, 0xff)
TOGGLE_OFF_TEXT = QColor(0x88, 0x88, 0x88)
CONFIRM_BG = QColor(0x2a, 0x1a, 0x1a)
CONFIRM_TEXT = QColor(0xe7, 0x4c, 0x3c)
CONFIRM_BORDER = QColor(0xe7, 0x4c, 0x3c)
CHEVRON_COLOR = QColor(0x55, 0x55, 0x55)
CHEVRON_HL = QColor(0xe6, 0x7e, 0x22)

TAB_HEIGHT = 28
ITEM_HEIGHT = 26
ACCENT_WIDTH = 3
TOGGLE_WIDTH = 50
CHEVRON_WIDTH = 40
PADDING_LEFT = 12
PADDING_RIGHT = 12


class OverlayWindow(QWidget):
    """Frameless Qt window that renders a widget's current page."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._widget = None
        self._font = QFont("Sans", 10)
        self._font_bold = QFont("Sans", 10)
        self._font_bold.setBold(True)
        self._font_small = QFont("Sans", 8)
        self._font_tab = QFont("Sans", 9)
        self._font_tab_bold = QFont("Sans", 9)
        self._font_tab_bold.setBold(True)

    def set_widget(self, widget):
        """Attach a widget and position/size the window."""
        self._widget = widget
        x, y, w, h = widget.position
        self.move(x, y)
        self.resize(w, h)

    def paintEvent(self, event):
        if not self._widget:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self.width()
        h = self.height()

        # Background
        p.fillRect(0, 0, w, h, BG)

        # Tab bar
        self._paint_tabs(p, w)

        # Items
        self._paint_items(p, w, h)

        p.end()

    def _paint_tabs(self, p, w):
        """Draw the page tab bar."""
        p.fillRect(0, 0, w, TAB_HEIGHT, TAB_BAR_BG)
        num_pages = len(self._widget.pages)
        if num_pages == 0:
            return
        tab_w = w // max(num_pages, 1)
        for i, page in enumerate(self._widget.pages):
            x = i * tab_w
            is_active = (i == self._widget.current_page)
            if is_active:
                p.setPen(TAB_ACTIVE)
                p.setFont(self._font_tab_bold)
                # Active underline
                p.fillRect(x, TAB_HEIGHT - 2, tab_w, 2, TAB_ACTIVE)
            else:
                p.setPen(TAB_INACTIVE)
                p.setFont(self._font_tab)
            rect = QRect(x, 0, tab_w, TAB_HEIGHT)
            p.drawText(rect, Qt.AlignCenter, page.title)

    def _paint_items(self, p, w, h):
        """Draw the item list for the current page."""
        page = self._widget.page
        y = TAB_HEIGHT
        for i, item in enumerate(page.items):
            is_hl = (i == self._widget.cursor)
            is_confirming = is_hl and self._widget.confirming
            item_rect = QRect(0, y, w, ITEM_HEIGHT)

            if is_confirming:
                self._paint_confirm_row(p, item_rect)
            elif is_hl:
                self._paint_highlighted_row(p, item_rect, item)
            else:
                self._paint_normal_row(p, item_rect, item)

            y += ITEM_HEIGHT

    def _paint_normal_row(self, p, rect, item):
        """Draw a non-highlighted item row."""
        if isinstance(item, InfoItem):
            self._paint_info_row(p, rect, item, highlighted=False)
            return

        p.setFont(self._font)
        p.setPen(ITEM_TEXT)
        label_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                           rect.width() - PADDING_LEFT - PADDING_RIGHT, rect.height())

        if isinstance(item, ToggleItem):
            label_rect.setWidth(label_rect.width() - TOGGLE_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            self._paint_toggle(p, rect, item.state)
        elif isinstance(item, ActionItem):
            label_rect.setWidth(label_rect.width() - CHEVRON_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            chev_rect = QRect(rect.right() - CHEVRON_WIDTH, rect.y(),
                              CHEVRON_WIDTH, rect.height())
            p.setPen(CHEVRON_COLOR)
            p.drawText(chev_rect, Qt.AlignCenter, "\u203a")

    def _paint_highlighted_row(self, p, rect, item):
        """Draw a highlighted (cursor) item row."""
        # Background + accent border
        p.fillRect(rect, ITEM_BG_HL)
        p.fillRect(rect.x(), rect.y(), ACCENT_WIDTH, rect.height(), ACCENT)

        if isinstance(item, InfoItem):
            self._paint_info_row(p, rect, item, highlighted=True)
            return

        p.setFont(self._font_bold)
        p.setPen(ITEM_TEXT_HL)
        label_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                           rect.width() - PADDING_LEFT - PADDING_RIGHT, rect.height())

        if isinstance(item, ToggleItem):
            label_rect.setWidth(label_rect.width() - TOGGLE_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            self._paint_toggle(p, rect, item.state)
        elif isinstance(item, ActionItem):
            label_rect.setWidth(label_rect.width() - CHEVRON_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            chev_rect = QRect(rect.right() - CHEVRON_WIDTH, rect.y(),
                              CHEVRON_WIDTH, rect.height())
            p.setPen(CHEVRON_HL)
            p.drawText(chev_rect, Qt.AlignCenter, "\u203a")

    def _paint_info_row(self, p, rect, item, highlighted=False):
        """Draw an info row: label on left, value on right."""
        p.setFont(self._font)
        p.setPen(INFO_TEXT)
        label_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                           rect.width() // 2 - PADDING_LEFT, rect.height())
        p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)

        value = item.get_value()
        if value:
            value_rect = QRect(rect.width() // 2, rect.y(),
                               rect.width() // 2 - PADDING_RIGHT, rect.height())
            p.drawText(value_rect, Qt.AlignRight | Qt.AlignVCenter, value)

    def _paint_confirm_row(self, p, rect):
        """Draw the confirmation row."""
        p.fillRect(rect, CONFIRM_BG)
        p.fillRect(rect.x(), rect.y(), ACCENT_WIDTH, rect.height(), CONFIRM_BORDER)
        p.setFont(self._font_bold)
        p.setPen(CONFIRM_TEXT)
        text_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                          rect.width() - PADDING_LEFT - PADDING_RIGHT, rect.height())
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   "Are you sure? Push to confirm")

    def _paint_toggle(self, p, rect, state):
        """Draw a toggle pill at the right edge of the row."""
        pill_w = 40
        pill_h = 16
        pill_x = rect.right() - TOGGLE_WIDTH + (TOGGLE_WIDTH - pill_w) // 2
        pill_y = rect.y() + (rect.height() - pill_h) // 2

        bg = TOGGLE_ON_BG if state else TOGGLE_OFF_BG
        text_color = TOGGLE_ON_TEXT if state else TOGGLE_OFF_TEXT
        text = "ON" if state else "OFF"

        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, 8, 8)
        p.setPen(text_color)
        p.setFont(self._font_small)
        p.drawText(QRect(pill_x, pill_y, pill_w, pill_h), Qt.AlignCenter, text)
```

- [ ] **Step 2: Commit**

```bash
git add pi-setup/mk3_overlay/renderer.py
git commit -m "feat(overlay): add Qt overlay window with QPainter page renderer"
```

---

### Task 5: Settings widget (`widgets/settings.py`)

**Files:**
- Create: `pi-setup/mk3_overlay/widgets/__init__.py`
- Create: `pi-setup/mk3_overlay/widgets/settings.py`
- Create: `pi-setup/tests/test_settings.py`

The settings widget: three pages (General, Library, Network), system command execution, info value queries.

- [ ] **Step 1: Write failing tests for settings actions and info**

Create `pi-setup/tests/test_settings.py`:

```python
"""Tests for the Settings widget."""
import os
import unittest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mk3_overlay.widgets.settings import create_settings_widget


class TestSettingsPages(unittest.TestCase):
    """Test settings widget structure."""

    def test_has_three_pages(self):
        w = create_settings_widget()
        self.assertEqual(len(w.pages), 3)

    def test_page_titles(self):
        w = create_settings_widget()
        self.assertEqual(w.pages[0].title, "GENERAL")
        self.assertEqual(w.pages[1].title, "LIBRARY")
        self.assertEqual(w.pages[2].title, "NETWORK")

    def test_general_page_items(self):
        w = create_settings_widget()
        labels = [item.label for item in w.pages[0].items]
        self.assertEqual(labels, [
            "Reboot", "Shutdown", "Check for Updates",
            "Auto-update on boot", "Version",
        ])

    def test_reboot_requires_confirm(self):
        w = create_settings_widget()
        self.assertTrue(w.pages[0].items[0].confirm)

    def test_shutdown_requires_confirm(self):
        w = create_settings_widget()
        self.assertTrue(w.pages[0].items[1].confirm)

    def test_check_updates_no_confirm(self):
        w = create_settings_widget()
        self.assertFalse(w.pages[0].items[2].confirm)


class TestNetworkInfo(unittest.TestCase):
    """Test that info items return system values."""

    def test_hostname_info(self):
        w = create_settings_widget()
        hostname_item = w.pages[2].items[1]  # Hostname
        self.assertEqual(hostname_item.label, "Hostname")
        # value_fn should call socket.gethostname
        with patch("socket.gethostname", return_value="mk3-pi"):
            self.assertEqual(hostname_item.get_value(), "mk3-pi")

    def test_ip_address_info(self):
        w = create_settings_widget()
        ip_item = w.pages[2].items[0]
        self.assertEqual(ip_item.label, "IP Address")

    def test_wifi_info(self):
        w = create_settings_widget()
        wifi_item = w.pages[2].items[2]
        self.assertEqual(wifi_item.label, "WiFi Network")


class TestAutoupdateToggle(unittest.TestCase):
    """Test auto-update toggle behavior."""

    @patch("builtins.open", MagicMock())
    def test_toggle_on_writes_config(self):
        w = create_settings_widget()
        toggle = w.pages[0].items[3]  # Auto-update on boot
        self.assertFalse(toggle.state)
        w.execute_item()  # cursor starts at 0 (Reboot), need to move
        # Navigate to auto-update (index 3): down, down (skip info), down
        w.cursor = 3
        w.execute_item()
        self.assertTrue(toggle.state)

    @patch("os.path.exists", return_value=True)
    @patch("os.remove")
    def test_toggle_off_removes_config(self, mock_rm, mock_exists):
        w = create_settings_widget()
        toggle = w.pages[0].items[3]
        toggle.state = True
        w.cursor = 3
        w.execute_item()
        self.assertFalse(toggle.state)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/test_settings.py -v`
Expected: `ModuleNotFoundError: No module named 'mk3_overlay.widgets'`

- [ ] **Step 3: Implement settings widget**

Create `pi-setup/mk3_overlay/widgets/__init__.py` (empty file).

Create `pi-setup/mk3_overlay/widgets/settings.py`:

```python
"""Settings widget for the MK3 overlay system.

Three pages: General, Library, Network.
Executes system commands directly (sudo reboot, etc.).
Info items query live system state on page enter.
"""
import os
import socket
import subprocess

from ..widget import Widget, Page, ActionItem, ToggleItem, InfoItem
from .. import focus

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # pi-setup/
AUTOUPDATE_FILE = "/etc/mk3-autoupdate"


def _run(args):
    """Run a command, ignoring errors."""
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def _run_wait(args):
    """Run a command and wait for completion. Returns stdout or empty string."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _get_ip():
    try:
        return _run_wait(["hostname", "-I"]).split()[0]
    except (IndexError, Exception):
        return "unknown"


def _get_hostname():
    return socket.gethostname()


def _get_wifi():
    return _run_wait(["iwgetid", "-r"]) or "not connected"


def _get_version():
    version_file = os.path.join(PROJECT_DIR, "VERSION")
    if os.path.exists(version_file):
        try:
            with open(version_file) as f:
                return f.read().strip()
        except IOError:
            pass
    # Try git
    result = _run_wait(["git", "-C", PROJECT_DIR, "describe", "--tags", "--always"])
    return result or "unknown"


def _get_library_location():
    # Mixxx default library path
    home = os.path.expanduser("~")
    mixxx_lib = os.path.join(home, ".mixxx", "mixxxdb.sqlite")
    if os.path.exists(mixxx_lib):
        return os.path.dirname(mixxx_lib)
    return "~/.mixxx"


def _autoupdate_enabled():
    return os.path.exists(AUTOUPDATE_FILE)


def _on_autoupdate_toggle(state):
    if state:
        try:
            with open(AUTOUPDATE_FILE, "w") as f:
                f.write("1\n")
        except IOError:
            pass
    else:
        try:
            os.remove(AUTOUPDATE_FILE)
        except OSError:
            pass


def _on_tailscale_toggle(state):
    if state:
        _run(["sudo", "tailscale", "up"])
    else:
        _run(["sudo", "tailscale", "down"])


def _do_reboot():
    _run(["sudo", "reboot"])


def _do_shutdown():
    _run(["sudo", "shutdown", "-h", "now"])


def _do_update():
    update_script = os.path.join(PROJECT_DIR, "mk3-update.sh")
    _run(["sudo", "bash", update_script])


def _do_rescan():
    focus.send_rescan()


def _do_mount_usb():
    try:
        result = subprocess.run(
            ["lsblk", "-rno", "NAME,TYPE,MOUNTPOINT"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "part":
                name = parts[0]
                mountpoint = parts[2] if len(parts) > 2 else ""
                if mountpoint in ("/", "/boot", "/boot/firmware"):
                    continue
                if not mountpoint:
                    dev = f"/dev/{name}"
                    mount_dir = f"/media/usb-{name}"
                    os.makedirs(mount_dir, exist_ok=True)
                    subprocess.run(["sudo", "mount", dev, mount_dir], timeout=10)
                    return
    except (subprocess.TimeoutExpired, Exception):
        pass


def _do_unmount_usb():
    import glob as g
    for mount_dir in g.glob("/media/usb-*"):
        try:
            subprocess.run(["sudo", "umount", mount_dir], timeout=10)
            os.rmdir(mount_dir)
        except (subprocess.TimeoutExpired, OSError):
            pass


def _stub():
    """Placeholder for not-yet-implemented actions."""
    pass


def create_settings_widget(position=None):
    """Create and return the settings widget with all three pages configured."""
    pos = position or (0, 0, 480, 272)

    general = Page(title="GENERAL", items=[
        ActionItem(label="Reboot", on_execute=_do_reboot, confirm=True),
        ActionItem(label="Shutdown", on_execute=_do_shutdown, confirm=True),
        ActionItem(label="Check for Updates", on_execute=_do_update),
        ToggleItem(label="Auto-update on boot",
                   state=_autoupdate_enabled(),
                   on_toggle=_on_autoupdate_toggle),
        InfoItem(label="Version", value_fn=_get_version),
    ])

    library = Page(title="LIBRARY", items=[
        ActionItem(label="Rescan Library", on_execute=_do_rescan),
        ActionItem(label="Mount USB Drive", on_execute=_do_mount_usb),
        ActionItem(label="Unmount USB Drive", on_execute=_do_unmount_usb),
        InfoItem(label="Library Location", value_fn=_get_library_location),
    ])

    network = Page(title="NETWORK", items=[
        InfoItem(label="IP Address", value_fn=_get_ip),
        InfoItem(label="Hostname", value_fn=_get_hostname),
        InfoItem(label="WiFi Network", value_fn=_get_wifi),
        ActionItem(label="WiFi Select", on_execute=_stub),
        ToggleItem(label="Tailscale", state=False,
                   on_toggle=_on_tailscale_toggle),
        ToggleItem(label="Hotspot", state=False, on_toggle=lambda s: None),
    ])

    return Widget(
        name="settings",
        position=pos,
        activate_button="settings",
        pages=[general, library, network],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/test_settings.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pi-setup/mk3_overlay/widgets/__init__.py pi-setup/mk3_overlay/widgets/settings.py pi-setup/tests/test_settings.py
git commit -m "feat(overlay): add settings widget with 3 pages and system commands"
```

---

### Task 6: Daemon entry point (`daemon.py`)

**Files:**
- Create: `pi-setup/mk3_overlay/daemon.py`

The main daemon: initializes QApplication, discovers HID, runs a QTimer poll loop, manages widget activation/deactivation, routes input to the active widget.

- [ ] **Step 1: Implement daemon.py**

Create `pi-setup/mk3_overlay/daemon.py`:

```python
#!/usr/bin/env python3
"""MK3 Overlay Widget System daemon.

Reads HID input from the MK3, manages widget lifecycle, renders Qt overlay
windows on Xvfb :99, and coordinates with Mixxx/T9/mouse via focus trapping.
"""
import os
import sys
import signal
import argparse
import time

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from .hid import find_hidraw, open_hidraw, read_report, parse_buttons, parse_stepper, parse_knob, LedWriter, KNOBS
from .widget import ActionItem, ToggleItem
from .renderer import OverlayWindow
from . import focus
from .widgets.settings import create_settings_widget

LOG_PREFIX = "mk3-overlay"
POLL_INTERVAL_MS = 16  # ~60Hz
RECONNECT_DELAY_MS = 3000
CONFIRM_TIMEOUT_MS = 5000


def log(msg):
    print(f"{LOG_PREFIX}: {msg}", file=sys.stderr, flush=True)


class OverlayDaemon:
    """Main daemon: HID poll loop, widget manager, Qt window lifecycle."""

    def __init__(self, device_path=None):
        self._device_path = device_path
        self._fd = None
        self._prev_report = bytes(64)
        self._leds = None
        self._active_widget = None
        self._widgets = {}
        self._window = OverlayWindow()
        self._confirm_timer = None

        # Poll timer
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)

        # Reconnect timer
        self._reconnect_timer = QTimer()
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_connect)

    def register_widget(self, widget):
        """Register a widget by its activation button."""
        self._widgets[widget.activate_button] = widget

    def start(self):
        """Start the daemon: attempt HID connection and begin polling."""
        self._try_connect()

    def _try_connect(self):
        """Discover and open the HID device."""
        path = find_hidraw(self._device_path)
        if path is None:
            log("waiting for MK3 HID device...")
            self._reconnect_timer.start(RECONNECT_DELAY_MS)
            return

        try:
            self._fd = open_hidraw(path)
        except OSError as e:
            log(f"cannot open {path}: {e}")
            self._reconnect_timer.start(RECONNECT_DELAY_MS)
            return

        log(f"listening on {path}")
        self._prev_report = bytes(64)
        self._leds = LedWriter(self._fd)
        self._poll_timer.start(POLL_INTERVAL_MS)

    def _disconnect(self):
        """Close the HID device and schedule reconnect."""
        self._poll_timer.stop()
        if self._active_widget:
            self._deactivate_widget()
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        self._leds = None
        log("HID read error, reconnecting...")
        self._reconnect_timer.start(RECONNECT_DELAY_MS)

    def _poll(self):
        """Read one HID report and process it."""
        report = read_report(self._fd)
        if report is None:
            return
        if len(report) == 0:
            self._disconnect()
            return

        report_id = report[0]
        if report_id != 0x01:
            self._prev_report = report
            return

        pressed, released = parse_buttons(report, self._prev_report)

        # Check activation buttons (always, even when a widget is active)
        for btn_name, widget in self._widgets.items():
            if btn_name in pressed:
                if self._active_widget is widget:
                    self._deactivate_widget()
                    self._prev_report = report
                    return
                elif self._active_widget is None:
                    self._activate_widget(widget)
                    self._prev_report = report
                    return

        # Route input to active widget
        if self._active_widget:
            self._handle_widget_input(pressed, released, report)

        self._prev_report = report

    def _activate_widget(self, widget):
        """Show a widget's overlay window and take focus."""
        self._active_widget = widget
        widget.on_activate()
        focus.activate()
        self._window.set_widget(widget)
        self._window.show()
        self._window.update()
        self._update_leds()
        log(f"widget '{widget.name}' activated")

    def _deactivate_widget(self):
        """Hide the overlay window and release focus."""
        name = self._active_widget.name
        self._active_widget.on_deactivate()
        self._active_widget = None
        self._cancel_confirm_timer()
        focus.deactivate()
        self._window.hide()
        if self._leds:
            self._leds.all_off()
            self._leds.send()
        log(f"widget '{name}' deactivated")

    def _handle_widget_input(self, pressed, released, report):
        """Route HID input to the active widget."""
        w = self._active_widget
        repaint = False

        # Nav up/down and stepper: cursor movement
        if "navUp" in pressed:
            w.move_cursor(-1)
            self._cancel_confirm_timer()
            repaint = True
        if "navDown" in pressed:
            w.move_cursor(1)
            self._cancel_confirm_timer()
            repaint = True

        # Stepper
        stepper_delta = parse_stepper(report, self._prev_report)
        if stepper_delta != 0:
            w.move_cursor(-1 if stepper_delta < 0 else 1)
            self._cancel_confirm_timer()
            repaint = True

        # Arrow left/right: page switching
        if "arrowLeft" in pressed:
            w.switch_page(-1)
            self._cancel_confirm_timer()
            repaint = True
        if "arrowRight" in pressed:
            w.switch_page(1)
            self._cancel_confirm_timer()
            repaint = True

        # D buttons: jump to page
        for i in range(1, 9):
            d_name = f"d{i}"
            if d_name in pressed:
                page_idx = i - 1
                if page_idx < len(w.pages):
                    w.jump_to_page(page_idx)
                    self._cancel_confirm_timer()
                    repaint = True
                break

        # Nav push: execute
        if "navPush" in pressed:
            was_confirming = w.confirming
            w.execute_item()
            if w.confirming and not was_confirming:
                self._start_confirm_timer()
            elif not w.confirming:
                self._cancel_confirm_timer()
            repaint = True

        # Knob input
        for knob_name in KNOBS:
            delta = parse_knob(report, self._prev_report, knob_name)
            if delta != 0:
                bindings = w.page.knob_bindings
                if knob_name in bindings:
                    bindings[knob_name](delta)
                    repaint = True

        if repaint:
            self._window.update()
            self._update_leds()

    def _update_leds(self):
        """Update LED state for the active widget."""
        if not self._leds or not self._active_widget:
            return
        w = self._active_widget

        self._leds.all_off()

        # Activation button bright
        self._leds.set_led(w.activate_button, 63)

        # D-buttons for page tabs
        for i, page in enumerate(w.pages):
            d_name = f"d{i + 1}"
            brightness = 63 if i == w.current_page else 16
            self._leds.set_led(d_name, brightness)

        self._leds.send()

    def _start_confirm_timer(self):
        """Start 5-second auto-cancel for confirmation."""
        self._cancel_confirm_timer()
        self._confirm_timer = QTimer()
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.timeout.connect(self._on_confirm_timeout)
        self._confirm_timer.start(CONFIRM_TIMEOUT_MS)

    def _cancel_confirm_timer(self):
        if self._confirm_timer:
            self._confirm_timer.stop()
            self._confirm_timer = None

    def _on_confirm_timeout(self):
        """Auto-cancel confirmation after timeout."""
        if self._active_widget:
            self._active_widget.cancel_confirm()
            self._window.update()
        self._confirm_timer = None


def main():
    parser = argparse.ArgumentParser(description="MK3 Overlay Widget System")
    parser.add_argument("--device", help="HID device path (default: auto-detect)")
    args = parser.parse_args()

    # Handle SIGTERM/SIGINT gracefully
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    app = QApplication(sys.argv)
    app.setApplicationName("mk3-overlay")

    daemon = OverlayDaemon(device_path=args.device)

    # Register widgets
    settings = create_settings_widget()
    daemon.register_widget(settings)

    daemon.start()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add pi-setup/mk3_overlay/daemon.py
git commit -m "feat(overlay): add daemon entry point with HID poll loop and widget manager"
```

---

### Task 7: Systemd service file

**Files:**
- Create: `pi-setup/mk3-overlay.service`

- [ ] **Step 1: Create service file**

Create `pi-setup/mk3-overlay.service`:

```ini
[Unit]
Description=MK3 Overlay Widget System
After=openbox.service
Requires=openbox.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:99
Environment=HOME=/home/pi
ExecStart=/usr/bin/python3 -m mk3_overlay.daemon
WorkingDirectory=/home/pi/mixx-mk3/pi-setup
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit**

```bash
git add pi-setup/mk3-overlay.service
git commit -m "feat(overlay): add systemd service unit"
```

---

### Task 8: Add overlay-active check to T9 and mouse daemons

**Files:**
- Modify: `pi-setup/mk3-t9-daemon.py`
- Modify: `pi-setup/mk3-mouse-daemon.py`

Both daemons need to skip input processing when `/tmp/mk3-overlay-active` exists.

- [ ] **Step 1: Add flag check to T9 daemon**

In `pi-setup/mk3-t9-daemon.py`, add constant near the top (after existing constants around line 55):

```python
OVERLAY_ACTIVE_FLAG = "/tmp/mk3-overlay-active"
```

Then in the main loop, after the `if not data: continue` check (around line 293), add the overlay check before processing report 0x01:

```python
                # Skip input when overlay widget has focus
                if os.path.exists(OVERLAY_ACTIVE_FLAG):
                    continue
```

This goes right before `report_id = data[0]` (line 295).

- [ ] **Step 2: Add flag check to mouse daemon**

In `pi-setup/mk3-mouse-daemon.py`, add constant near the top (after existing constants around line 67):

```python
OVERLAY_ACTIVE_FLAG = "/tmp/mk3-overlay-active"
```

Then in the main loop, after `if not data: continue` (around line 195), add:

```python
                # Skip input when overlay widget has focus
                if os.path.exists(OVERLAY_ACTIVE_FLAG):
                    continue
```

This goes right before `report_id = data[0]` (line 197).

- [ ] **Step 3: Commit**

```bash
git add pi-setup/mk3-t9-daemon.py pi-setup/mk3-mouse-daemon.py
git commit -m "feat(overlay): add overlay-active flag check to T9 and mouse daemons"
```

---

### Task 9: Update JS mapping — add overlay handlers, remove settings code

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

This is the largest change to existing code. We add the F10/F11/F12 keyboard handler and `overlayActive` guard, then remove all settings-related state, functions, and input handling.

- [ ] **Step 1: Add overlayActive state and F-key handler**

Replace the `settingsVisible` declaration and the settings state block (lines 306-342) with:

```javascript
MaschineMK3.overlayActive  = false;    // overlay widget has focus — suppress HID processing
```

Remove these lines entirely (they are no longer needed):
- `MaschineMK3.settingsVisible` through `MaschineMK3.settingsHotspot` (lines 306-342)
- `MaschineMK3.settingsNextSelectable` function (lines 346-356)
- `MaschineMK3.settingsFirstSelectable` function (lines 358-365)
- `MaschineMK3.updateSettingsSkinCOs` function (lines 510-524)
- `MaschineMK3.updateSettingsLEDs` function (lines 531-542)
- `MaschineMK3.settingsExecuteItem` function (lines 547-591)
- `MaschineMK3.settingsDispatchCommand` function (lines 594-603)
- `MaschineMK3.settingsTabs` definition (lines 315-337)

- [ ] **Step 2: Add overlayActive guard in incomingData**

In `MaschineMK3.incomingData` (around line 1438), add a guard right after the length check:

```javascript
MaschineMK3.incomingData = function(data, length) {
    if (length < 1) { return; }
    // Overlay widget has focus — skip HID processing
    if (MaschineMK3.overlayActive) { return; }
    var reportId = data[0];
    if (reportId === 0x01) {
        MaschineMK3.parseReport01(data);
    } else if (reportId === MaschineMK3.PAD_REPORT_ID) {
        MaschineMK3.parseReport02(data);
    }
};
```

- [ ] **Step 3: Remove settings from updatePanels**

In `MaschineMK3.updatePanels` (around line 469), remove all settings references:

Replace the function with:

```javascript
MaschineMK3.updatePanels = function() {
    var showLib = MaschineMK3.libraryVisible;
    var showMix = MaschineMK3.mixerVisible;
    var noPanelOpen = !showLib && !showMix;
    var showPadsLoops = noPanelOpen && MaschineMK3.padMode === "loops";
    var showPadsFx = noPanelOpen && MaschineMK3.padMode === "effects";
    var showPadsCues = noPanelOpen && MaschineMK3.padMode === "cuepoints";
    var anyPanel = showLib || showMix || showPadsLoops || showPadsFx || showPadsCues;

    engine.setValue("[Skin]", "show_library", showLib ? 1 : 0);
    engine.setValue("[Skin]", "show_mixer", showMix ? 1 : 0);
    engine.setValue("[Skin]", "show_t9", showLib ? 1 : 0);
    engine.setValue("[Skin]", "show_pads_loops", showPadsLoops ? 1 : 0);
    engine.setValue("[Skin]", "show_pads_fx", showPadsFx ? 1 : 0);
    engine.setValue("[Skin]", "show_pads_cues", showPadsCues ? 1 : 0);

    if (showLib) {
        engine.setValue("[Skin]", "hide_deck_a", 1);
        engine.setValue("[Skin]", "hide_deck_b", 1);
    } else {
        engine.setValue("[Skin]", "hide_deck_a", (anyPanel && MaschineMK3.activeDeck === 2) ? 1 : 0);
        engine.setValue("[Skin]", "hide_deck_b", (anyPanel && MaschineMK3.activeDeck === 1) ? 1 : 0);
    }

    MaschineMK3.setLed("browserPlugin", showLib ? 63 : 16);
    MaschineMK3.setLed("mixer", showMix ? 63 : 16);

    if (showLib) {
        engine.setValue("[Library]", "focused_widget", 1);
    }
};
```

- [ ] **Step 4: Remove settings from button handlers**

In the `case "settings":` handler (around line 992), replace the settings toggle block with a no-op (the overlay daemon handles this now):

```javascript
    case "settings":
        // Handled by mk3-overlay daemon
        break;
```

In `case "browserPlugin":` (around line 966), remove `MaschineMK3.settingsVisible = false;`.

In `case "mixer":` (around line 981), remove `MaschineMK3.settingsVisible = false;`.

In `case "padMode":` (around line 884), remove `MaschineMK3.settingsVisible = false;`.

In `case "performFxSelect":` (around line 905), remove `MaschineMK3.settingsVisible = false;`.

- [ ] **Step 5: Remove settings from nav handlers**

In `case "navUp":` (around line 1011), remove the settings branch. Keep only:

```javascript
    case "navUp":
        engine.setValue("[Library]", "MoveUp", 1);
        break;
```

In `case "navDown":` (around line 1021), same:

```javascript
    case "navDown":
        engine.setValue("[Library]", "MoveDown", 1);
        break;
```

In `case "navLeft":` (around line 1031), remove the `!settingsVisible` guard:

```javascript
    case "navLeft":
        engine.setValue("[Library]", "MoveFocusBackward", 1);
        break;
```

In `case "navRight":` (around line 1036), same:

```javascript
    case "navRight":
        engine.setValue("[Library]", "MoveFocusForward", 1);
        break;
```

In `case "navPush":` (around line 1041), remove the `settingsVisible` branch:

```javascript
    case "navPush":
        if (MaschineMK3.libraryVisible) {
            var focus = engine.getValue("[Library]", "focused_widget");
            if (focus === 1) {
                engine.setValue("[Library]", "focused_widget", 3);
            } else {
                engine.setValue("[Channel" + MaschineMK3.activeDeck + "]", "LoadSelectedTrack", 1);
                MaschineMK3.libraryVisible = false;
                MaschineMK3.padMode = null;
                MaschineMK3.updatePadModeLED();
                MaschineMK3.updatePadLEDs();
                MaschineMK3.updatePanels();
            }
        }
        break;
```

- [ ] **Step 6: Remove settings from D-button handlers**

In the `case "d1": case "d2":...` handler (around line 916), remove the settings tab-switching block. Keep only the normal DJ mode behavior:

```javascript
    case "d1": case "d2": case "d3": case "d4":
    case "d5": case "d6": case "d7": case "d8":
        var dNum = parseInt(name.charAt(1), 10);
        if (dNum === 1) {
            engine.setValue("[Channel1]", "sync_enabled",
                engine.getValue("[Channel1]", "sync_enabled") ? 0 : 1);
        } else if (dNum === 5) {
            engine.setValue("[Channel2]", "sync_enabled",
                engine.getValue("[Channel2]", "sync_enabled") ? 0 : 1);
        } else if (dNum === 2) {
            engine.setValue("[Channel1]", "rate_temp_down", 1);
        } else if (dNum === 6) {
            engine.setValue("[Channel2]", "rate_temp_down", 1);
        } else if (dNum === 3) {
            engine.setValue("[Channel1]", "rate_temp_up", 1);
        } else if (dNum === 7) {
            engine.setValue("[Channel2]", "rate_temp_up", 1);
        } else if (dNum === 4) {
            engine.setValue("[Channel1]", "pfl", engine.getValue("[Channel1]", "pfl") ? 0 : 1);
        } else if (dNum === 8) {
            engine.setValue("[Channel2]", "pfl", engine.getValue("[Channel2]", "pfl") ? 0 : 1);
        }
        break;
```

- [ ] **Step 7: Remove settings from D-button releases and stepper**

In `onButtonRelease`, replace `!MaschineMK3.settingsVisible` guards (around lines 1096-1105) with plain calls:

```javascript
    case "d2":
        engine.setValue("[Channel1]", "rate_temp_down", 0);
        break;
    case "d3":
        engine.setValue("[Channel1]", "rate_temp_up", 0);
        break;
    case "d6":
        engine.setValue("[Channel2]", "rate_temp_down", 0);
        break;
    case "d7":
        engine.setValue("[Channel2]", "rate_temp_up", 0);
        break;
```

In `onStepperChange` (around line 1235), remove the settings cursor block. Keep only:

```javascript
MaschineMK3.onStepperChange = function(direction) {
    if (MaschineMK3.mouseMode) { return; }
    if (direction > 0) {
        engine.setValue("[Library]", "MoveDown", 1);
        engine.setValue("[Library]", "MoveDown", 0);
    } else {
        engine.setValue("[Library]", "MoveUp", 1);
        engine.setValue("[Library]", "MoveUp", 0);
    }
};
```

- [ ] **Step 8: Remove settings LED from init**

In `init()` (around line 1552), remove the line:

```javascript
    MaschineMK3.setLed("settings", 16);
```

The overlay daemon manages the settings LED now.

- [ ] **Step 9: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "refactor(js): remove settings UI code, add overlay active guard"
```

---

### Task 10: Remove settings from skin XML and QSS

**Files:**
- Modify: `skin/MK3/skin.xml`
- Modify: `skin/MK3/style.qss`

- [ ] **Step 1: Remove settings CO attributes from skin.xml**

Remove these lines (23-36) from the `<attributes>` block:

```xml
      <attribute config_key="[Skin],show_settings">0</attribute>
      <attribute config_key="[Skin],settings_tab_0">1</attribute>
      <attribute config_key="[Skin],settings_tab_1">0</attribute>
      <attribute config_key="[Skin],settings_tab_2">0</attribute>
      <attribute config_key="[Skin],settings_cursor_0">1</attribute>
      <attribute config_key="[Skin],settings_cursor_1">0</attribute>
      <attribute config_key="[Skin],settings_cursor_2">0</attribute>
      <attribute config_key="[Skin],settings_cursor_3">0</attribute>
      <attribute config_key="[Skin],settings_cursor_4">0</attribute>
      <attribute config_key="[Skin],settings_cursor_5">0</attribute>
      <attribute config_key="[Skin],settings_confirming">0</attribute>
      <attribute config_key="[Skin],settings_autoupdate">0</attribute>
      <attribute config_key="[Skin],settings_tailscale">0</attribute>
      <attribute config_key="[Skin],settings_hotspot">0</attribute>
```

- [ ] **Step 2: Remove SettingsPanel widget group from skin.xml**

Remove the entire `<!-- ═══════ SETTINGS PANEL (480x272) ═══════ -->` block — from the comment through its closing `</WidgetGroup>`. This is the block starting with `<ObjectName>SettingsPanel</ObjectName>` and ending before `<!-- ═══════ PAD INFO: LOOPS`.

Also remove the `show_settings` reference from `updatePanels` — this was in JS, already handled in Task 9.

- [ ] **Step 3: Remove Settings styles from style.qss**

Remove everything from `/* ── Settings Panel */` through `#SettingsConfirm { ... }` — all style rules prefixed with `#Settings`.

- [ ] **Step 4: Commit**

```bash
git add skin/MK3/skin.xml skin/MK3/style.qss
git commit -m "refactor(skin): remove settings panel and settings COs"
```

---

### Task 11: Remove obsolete files

**Files:**
- Delete: `pi-setup/mk3-settings-watcher.py`
- Delete: `pi-setup/mk3-settings-watcher.service`
- Delete: `pi-setup/mk3-settings-menu.sh`

- [ ] **Step 1: Remove files**

```bash
git rm pi-setup/mk3-settings-watcher.py pi-setup/mk3-settings-watcher.service pi-setup/mk3-settings-menu.sh
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: remove obsolete settings watcher, menu, and service files"
```

---

### Task 12: Update setup script

**Files:**
- Modify: `pi-setup/mk3-pi-setup.sh`

Add `python3-pyqt5` to dependencies, install `mk3-overlay.service` instead of `mk3-settings-watcher.service`, remove `mk3-settings-menu.sh` references.

- [ ] **Step 1: Add python3-pyqt5 to dependencies**

In the `apt-get install` block (around line 21), add `python3-pyqt5` to the package list.

- [ ] **Step 2: Update service installation**

Find where `mk3-settings-watcher.service` is installed (grep the file for references) and replace with `mk3-overlay.service`. Also ensure the service is enabled with `systemctl enable mk3-overlay.service`.

Remove any references to `mk3-settings-menu.sh` installation.

- [ ] **Step 3: Commit**

```bash
git add pi-setup/mk3-pi-setup.sh
git commit -m "chore(setup): install mk3-overlay service, add python3-pyqt5 dep"
```

---

### Task 13: Run full test suite

**Files:** None (verification only)

- [ ] **Step 1: Run all overlay tests**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -m pytest pi-setup/tests/ -v`
Expected: All tests pass (test_hid, test_widget, test_settings, and existing test_t9_engine)

- [ ] **Step 2: Verify no Python syntax errors in daemon**

Run: `cd /home/zeb/dev/mixx-mk3 && python3 -c "import pi-setup.mk3_overlay.daemon" 2>&1 || python3 -c "import sys; sys.path.insert(0, 'pi-setup'); from mk3_overlay import daemon"`

Note: Full daemon startup requires PyQt5 and a display — this just checks imports resolve.

- [ ] **Step 3: Commit any fixes if needed**

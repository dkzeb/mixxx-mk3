# Tempo Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a TEMPO button-activated panel with BPM/key controls, sync, and automated tempo ramping between decks.

**Architecture:** The tempo panel is a new skin panel (like the existing mixer panel) with JS-driven ramp automation via `engine.beginTimer()`. The panel shows on both screens simultaneously. Ramp timers run independently of panel visibility, with LED and on-screen indicators.

**Tech Stack:** Mixxx XML skin format, Mixxx JavaScript controller API (`engine.*`)

**Spec:** `docs/superpowers/specs/2026-04-05-tempo-panel-design.md`

---

### Task 1: Add tempo state and constants to JS mapping

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js:8` (after `var MaschineMK3 = {};`)

- [ ] **Step 1: Add ramp constants and tempo state initialization**

After line 8 (`var MaschineMK3 = {};`), add the ramp configuration constants:

```javascript
// --- Tempo ramp configuration ---
var RAMP_BPM_PER_SEC = 2.0;
var RAMP_INTERVAL_MS = 50;
var RAMP_THRESHOLD_BPM = 0.05;
var RAMP_MULTIPLIERS = [1.0, 0.5, 2.0];
var RAMP_TARGET_STEP_THRESHOLD = 400;
```

Then after the existing panel state variables (search for `MaschineMK3.stemMixerVisible`), add:

```javascript
MaschineMK3.tempoVisible = false;
MaschineMK3.tempoState = {
    rampTimerA: 0,
    rampTimerB: 0,
    rampMultiplierA: 0,
    rampMultiplierB: 0,
    rampTargetAccumA: 0,
    rampTargetAccumB: 0,
    rampLedTimer: 0,
    rampLedState: false,
};
```

- [ ] **Step 2: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 3: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): add ramp constants and tempo state"
```

---

### Task 2: Add toggleTempoPanel() and update mutual exclusion in updatePanels()

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

- [ ] **Step 1: Add toggleTempoPanel function**

Add before the `updatePanels` function (around line 500):

```javascript
// ---------------------------------------------------------------------------
// toggleTempoPanel — show/hide tempo panel on both screens.
// ---------------------------------------------------------------------------
MaschineMK3.toggleTempoPanel = function() {
    MaschineMK3.tempoVisible = !MaschineMK3.tempoVisible;
    if (MaschineMK3.tempoVisible) {
        MaschineMK3.libraryVisible = false;
        MaschineMK3.mixerVisible = false;
        MaschineMK3.stemMixerVisible = false;
        MaschineMK3.cueDisplayVisible = false;
        MaschineMK3.setLed("notes", 0);
        if (MaschineMK3.padMode === "t9") { MaschineMK3.padMode = "cuepoints"; }
        MaschineMK3.updatePadModeLED();
        MaschineMK3.updatePadLEDs();
    }
    MaschineMK3.updateTempoLed();
    MaschineMK3.updatePanels();
};
```

- [ ] **Step 2: Add updateTempoLed helper**

Add right after `toggleTempoPanel`:

```javascript
// ---------------------------------------------------------------------------
// updateTempoLed — set TEMPO button LED based on panel and ramp state.
// ---------------------------------------------------------------------------
MaschineMK3.updateTempoLed = function() {
    var anyRamp = MaschineMK3.tempoState.rampTimerA || MaschineMK3.tempoState.rampTimerB;
    if (anyRamp) {
        // LED pulse is managed by rampLedTimer — don't override here
        return;
    }
    MaschineMK3.setLed("tempo", MaschineMK3.tempoVisible ? 63 : 0);
};
```

- [ ] **Step 3: Update updatePanels() for tempo panel**

In `updatePanels()`, modify the `noPanelOpen` line to include tempo:

Change:
```javascript
var noPanelOpen = !showLib && !showMix && !showStemMix;
```
To:
```javascript
var showTempo = MaschineMK3.tempoVisible;
var noPanelOpen = !showLib && !showMix && !showStemMix && !showTempo;
```

After the existing `engine.setValue("[Skin]", "show_stem_mixer", ...)` line, add:
```javascript
engine.setValue("[Skin]", "show_tempo", showTempo ? 1 : 0);
```

In the `if (showLib)` block, after the existing `hide_deck_a/b` logic, add an `else if` for tempo before the final `else`:

Change the block:
```javascript
if (showLib) {
    // Library: always left screen, T9 pad overview: always right screen
    engine.setValue("[Skin]", "hide_deck_a", 1);
    engine.setValue("[Skin]", "hide_deck_b", 1);
} else {
    // Other panels: replace non-active deck
    engine.setValue("[Skin]", "hide_deck_a", (anyPanel && MaschineMK3.activeDeck === 2) ? 1 : 0);
    engine.setValue("[Skin]", "hide_deck_b", (anyPanel && MaschineMK3.activeDeck === 1) ? 1 : 0);
}
```

To:
```javascript
if (showLib || showTempo) {
    // Library + Tempo: both screens replaced
    engine.setValue("[Skin]", "hide_deck_a", 1);
    engine.setValue("[Skin]", "hide_deck_b", 1);
} else {
    // Other panels: replace non-active deck
    engine.setValue("[Skin]", "hide_deck_a", (anyPanel && MaschineMK3.activeDeck === 2) ? 1 : 0);
    engine.setValue("[Skin]", "hide_deck_b", (anyPanel && MaschineMK3.activeDeck === 1) ? 1 : 0);
}
```

- [ ] **Step 4: Close tempo panel from other panel openers**

In the `"browserPlugin"` case (around line 983), inside the `if (MaschineMK3.libraryVisible)` block, add:
```javascript
MaschineMK3.tempoVisible = false;
```

In the `"mixer"` case (around line 1012), inside both the `if (MaschineMK3.stemMixerVisible)` and `if (MaschineMK3.mixerVisible)` blocks, add:
```javascript
MaschineMK3.tempoVisible = false;
```

In the `"notes"` case (around line 901), inside the `if (MaschineMK3.cueDisplayVisible)` block, add:
```javascript
MaschineMK3.tempoVisible = false;
```

In the `"performFxSelect"` case (around line 913), inside the `if (MaschineMK3.padMode !== "cuepoints")` block, add:
```javascript
MaschineMK3.tempoVisible = false;
```

- [ ] **Step 5: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 6: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): add panel toggle and mutual exclusion"
```

---

### Task 3: Add TEMPO button handler and D-button routing

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

- [ ] **Step 1: Add TEMPO button case in onButtonPress**

In `onButtonPress()`, add a case before the `"settings"` case (around line 1033):

```javascript
    // --- Tempo: toggle tempo panel ---
    case "tempo":
        MaschineMK3.toggleTempoPanel();
        break;
```

- [ ] **Step 2: Add D-button routing for tempo panel**

In the D-button handling section of `onButtonPress()` (the `case "d1": case "d2": ...` block, around line 934), add a tempo panel check after the library check but before the normal DJ mode behavior.

After the library-related `if` blocks (after line 949 `}`), add:

```javascript
        // Tempo panel D-button routing
        if (MaschineMK3.tempoVisible) {
            if (dNum === 1) {
                engine.setValue("[Channel1]", "sync_enabled",
                    engine.getValue("[Channel1]", "sync_enabled") ? 0 : 1);
            } else if (dNum === 5) {
                engine.setValue("[Channel2]", "sync_enabled",
                    engine.getValue("[Channel2]", "sync_enabled") ? 0 : 1);
            } else if (dNum === 2) {
                engine.setValue("[Channel1]", "keylock",
                    engine.getValue("[Channel1]", "keylock") ? 0 : 1);
            } else if (dNum === 6) {
                engine.setValue("[Channel2]", "keylock",
                    engine.getValue("[Channel2]", "keylock") ? 0 : 1);
            } else if (dNum === 3) {
                if (MaschineMK3.tempoState.rampTimerA) {
                    MaschineMK3.stopRamp(1);
                } else {
                    MaschineMK3.startRamp(1);
                }
            } else if (dNum === 7) {
                if (MaschineMK3.tempoState.rampTimerB) {
                    MaschineMK3.stopRamp(2);
                } else {
                    MaschineMK3.startRamp(2);
                }
            } else if (dNum === 4) {
                engine.setValue("[Channel1]", "rate", 0);
            } else if (dNum === 8) {
                engine.setValue("[Channel2]", "rate", 0);
            }
            break;
        }
```

- [ ] **Step 3: Guard D-button releases for tempo panel**

In `onButtonRelease()`, the D2/D3/D6/D7 releases currently reset `rate_temp_down/up` to 0. These should NOT fire when the tempo panel is open (since those buttons do different things). Wrap the existing release handlers (around lines 1113-1125):

Change:
```javascript
    // D button releases — tempo nudge (momentary)
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

To:
```javascript
    // D button releases — tempo nudge (momentary, only in normal mode)
    case "d2":
        if (!MaschineMK3.tempoVisible) { engine.setValue("[Channel1]", "rate_temp_down", 0); }
        break;
    case "d3":
        if (!MaschineMK3.tempoVisible) { engine.setValue("[Channel1]", "rate_temp_up", 0); }
        break;
    case "d6":
        if (!MaschineMK3.tempoVisible) { engine.setValue("[Channel2]", "rate_temp_down", 0); }
        break;
    case "d7":
        if (!MaschineMK3.tempoVisible) { engine.setValue("[Channel2]", "rate_temp_up", 0); }
        break;
```

- [ ] **Step 4: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 5: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): add button handler and D-button routing"
```

---

### Task 4: Add knob routing for tempo panel (K2/K6 key adjust, K4/K8 ramp target)

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

- [ ] **Step 1: Add tempo panel knob routing in getKnobBinding**

In `getKnobBinding()` (around line 1149), add a tempo panel check after the `stemMixerVisible` check and before the `mixerVisible` check:

```javascript
    if (MaschineMK3.tempoVisible) {
        switch (knobName) {
        case "k1": return {group: "[Channel1]", key: "rate"};
        case "k2": return {group: "[Channel1]", key: "pitch_adjust"};
        case "k5": return {group: "[Channel2]", key: "rate"};
        case "k6": return {group: "[Channel2]", key: "pitch_adjust"};
        }
        // K3/K7 unused, K4/K8 handled separately (ramp target selector)
        return null;
    }
```

- [ ] **Step 2: Add tempo panel knob handling in onKnobDelta**

In `onKnobDelta()`, add a tempo panel block before the `if (MaschineMK3.mixerVisible)` check (around line 1281):

```javascript
    if (MaschineMK3.tempoVisible) {
        switch (name) {
        case "k1":
            MaschineMK3.adjustValue("[Channel1]", "rate", delta, 0.002, -1, 1);
            break;
        case "k2":
            MaschineMK3.adjustValue("[Channel1]", "pitch_adjust", delta, 0.01, -6, 6);
            break;
        case "k4":
            MaschineMK3.handleRampTargetKnob(1, delta);
            break;
        case "k5":
            MaschineMK3.adjustValue("[Channel2]", "rate", delta, 0.002, -1, 1);
            break;
        case "k6":
            MaschineMK3.adjustValue("[Channel2]", "pitch_adjust", delta, 0.01, -6, 6);
            break;
        case "k8":
            MaschineMK3.handleRampTargetKnob(2, delta);
            break;
        }
        return;
    }
```

- [ ] **Step 3: Add handleRampTargetKnob function**

Add after the `updateTempoLed` function:

```javascript
// ---------------------------------------------------------------------------
// handleRampTargetKnob — sticky knob for ramp target selection.
// Accumulates knob delta and steps through multipliers when threshold crossed.
// ---------------------------------------------------------------------------
MaschineMK3.handleRampTargetKnob = function(deck, delta) {
    var key = (deck === 1) ? "rampTargetAccumA" : "rampTargetAccumB";
    var mulKey = (deck === 1) ? "rampMultiplierA" : "rampMultiplierB";
    MaschineMK3.tempoState[key] += delta;

    if (MaschineMK3.tempoState[key] >= RAMP_TARGET_STEP_THRESHOLD) {
        MaschineMK3.tempoState[key] = 0;
        if (MaschineMK3.tempoState[mulKey] < RAMP_MULTIPLIERS.length - 1) {
            MaschineMK3.tempoState[mulKey]++;
        }
    } else if (MaschineMK3.tempoState[key] <= -RAMP_TARGET_STEP_THRESHOLD) {
        MaschineMK3.tempoState[key] = 0;
        if (MaschineMK3.tempoState[mulKey] > 0) {
            MaschineMK3.tempoState[mulKey]--;
        }
    }
};
```

- [ ] **Step 4: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 5: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): add knob routing for key adjust and ramp target"
```

---

### Task 5: Implement the ramp engine (startRamp, stopRamp, rampTick)

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

- [ ] **Step 1: Add startRamp function**

Add after `handleRampTargetKnob`:

```javascript
// ---------------------------------------------------------------------------
// startRamp — begin ramping a deck toward the opposite deck's BPM × multiplier.
// ---------------------------------------------------------------------------
MaschineMK3.startRamp = function(deck) {
    var timerKey = (deck === 1) ? "rampTimerA" : "rampTimerB";

    // Disable sync on the ramping deck (sync would fight the ramp)
    engine.setValue("[Channel" + deck + "]", "sync_enabled", 0);

    MaschineMK3.tempoState[timerKey] = engine.beginTimer(RAMP_INTERVAL_MS, function() {
        MaschineMK3.rampTick(deck);
    });

    // Start LED pulse if not already running
    if (!MaschineMK3.tempoState.rampLedTimer) {
        MaschineMK3.tempoState.rampLedTimer = engine.beginTimer(500, function() {
            MaschineMK3.updateRampLed();
        });
    }

    // Show ramp indicator on deck screen
    engine.setValue("[Skin]", "show_ramp_" + (deck === 1 ? "a" : "b"), 1);

    // Update D-button LED
    MaschineMK3.setLed(deck === 1 ? "d3" : "d7", 63);
};
```

- [ ] **Step 2: Add stopRamp function**

```javascript
// ---------------------------------------------------------------------------
// stopRamp — stop ramping a deck. Cleans up timer, LED, indicators.
// ---------------------------------------------------------------------------
MaschineMK3.stopRamp = function(deck) {
    var timerKey = (deck === 1) ? "rampTimerA" : "rampTimerB";

    if (MaschineMK3.tempoState[timerKey]) {
        engine.stopTimer(MaschineMK3.tempoState[timerKey]);
        MaschineMK3.tempoState[timerKey] = 0;
    }

    // Hide ramp indicator on deck screen
    engine.setValue("[Skin]", "show_ramp_" + (deck === 1 ? "a" : "b"), 0);

    // Reset D-button LED
    MaschineMK3.setLed(deck === 1 ? "d3" : "d7", MaschineMK3.tempoVisible ? 16 : 16);

    // Stop LED pulse if no ramps active
    if (!MaschineMK3.tempoState.rampTimerA && !MaschineMK3.tempoState.rampTimerB) {
        if (MaschineMK3.tempoState.rampLedTimer) {
            engine.stopTimer(MaschineMK3.tempoState.rampLedTimer);
            MaschineMK3.tempoState.rampLedTimer = 0;
            MaschineMK3.tempoState.rampLedState = false;
        }
        MaschineMK3.updateTempoLed();
    }
};
```

- [ ] **Step 3: Add rampTick function**

```javascript
// ---------------------------------------------------------------------------
// rampTick — called every RAMP_INTERVAL_MS. Adjusts rate toward target BPM.
// ---------------------------------------------------------------------------
MaschineMK3.rampTick = function(deck) {
    var channel = "[Channel" + deck + "]";
    var oppDeck = (deck === 1) ? 2 : 1;
    var oppChannel = "[Channel" + oppDeck + "]";
    var mulKey = (deck === 1) ? "rampMultiplierA" : "rampMultiplierB";
    var multiplier = RAMP_MULTIPLIERS[MaschineMK3.tempoState[mulKey]];

    var currentBpm = engine.getValue(channel, "bpm");
    var oppBpm = engine.getValue(oppChannel, "bpm");
    var targetBpm = oppBpm * multiplier;

    var diff = targetBpm - currentBpm;

    // Check if we've reached the target
    if (Math.abs(diff) <= RAMP_THRESHOLD_BPM) {
        MaschineMK3.stopRamp(deck);
        return;
    }

    // Compute rate delta
    var bpmPerTick = RAMP_BPM_PER_SEC * (RAMP_INTERVAL_MS / 1000.0);
    var step = (diff > 0) ? Math.min(bpmPerTick, diff) : Math.max(-bpmPerTick, diff);

    var fileBpm = engine.getValue(channel, "file_bpm");
    var rateRange = engine.getValue(channel, "rateRange");

    if (fileBpm <= 0 || rateRange <= 0) {
        MaschineMK3.stopRamp(deck);
        return;
    }

    var currentRate = engine.getValue(channel, "rate");
    var rateDelta = step / (fileBpm * rateRange * 2);
    var newRate = currentRate + rateDelta;

    // Clamp to rate range and stop if we hit the limit
    if (newRate < -1) { newRate = -1; MaschineMK3.stopRamp(deck); }
    else if (newRate > 1) { newRate = 1; MaschineMK3.stopRamp(deck); }

    engine.setValue(channel, "rate", newRate);
};
```

- [ ] **Step 4: Add updateRampLed function**

```javascript
// ---------------------------------------------------------------------------
// updateRampLed — pulse TEMPO button LED while any ramp is active.
// ---------------------------------------------------------------------------
MaschineMK3.updateRampLed = function() {
    MaschineMK3.tempoState.rampLedState = !MaschineMK3.tempoState.rampLedState;
    MaschineMK3.setLed("tempo", MaschineMK3.tempoState.rampLedState ? 63 : 0);
};
```

- [ ] **Step 5: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 6: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): implement ramp engine with start/stop/tick"
```

---

### Task 6: Add ramp stop on track load and sync enable

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

- [ ] **Step 1: Stop ramp on track load**

Find the existing `onTrackLoaded` handler (around line 1630). It currently updates stem LEDs and panels. Add ramp stop logic inside it. The function currently looks like:

```javascript
MaschineMK3.onTrackLoaded = function(value, group) {
    if (value) {
        // ...existing stem/panel logic...
    }
};
```

Add at the start of the `if (value)` block:

```javascript
        // Stop any active ramp on this deck
        var loadedDeck = (group === "[Channel1]") ? 1 : 2;
        var timerKey = (loadedDeck === 1) ? "rampTimerA" : "rampTimerB";
        if (MaschineMK3.tempoState[timerKey]) {
            MaschineMK3.stopRamp(loadedDeck);
        }
```

- [ ] **Step 2: Stop ramp when sync is enabled on the ramping deck**

In the `init()` function, find the existing `sync_enabled` connections (around line 1658). After the existing LED feedback connections, add ramp-stop connections:

```javascript
    // Stop ramp if sync is enabled on the ramping deck
    engine.makeConnection("[Channel1]", "sync_enabled", function(value) {
        if (value && MaschineMK3.tempoState.rampTimerA) {
            MaschineMK3.stopRamp(1);
        }
    });
    engine.makeConnection("[Channel2]", "sync_enabled", function(value) {
        if (value && MaschineMK3.tempoState.rampTimerB) {
            MaschineMK3.stopRamp(2);
        }
    });
```

- [ ] **Step 3: Stop ramp timers in shutdown**

In `shutdown()` (around line 1765), before the LED blanking loop, add:

```javascript
    // Stop any active ramp timers
    if (MaschineMK3.tempoState.rampTimerA) { engine.stopTimer(MaschineMK3.tempoState.rampTimerA); }
    if (MaschineMK3.tempoState.rampTimerB) { engine.stopTimer(MaschineMK3.tempoState.rampTimerB); }
    if (MaschineMK3.tempoState.rampLedTimer) { engine.stopTimer(MaschineMK3.tempoState.rampLedTimer); }
```

- [ ] **Step 4: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 5: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): stop ramp on track load, sync enable, and shutdown"
```

---

### Task 7: Add D-button LED feedback for tempo panel

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js`

- [ ] **Step 1: Add tempo panel D-button LED update function**

Add after `updateTempoLed`:

```javascript
// ---------------------------------------------------------------------------
// updateTempoDButtonLEDs — set D-button LEDs for tempo panel state.
// ---------------------------------------------------------------------------
MaschineMK3.updateTempoDButtonLEDs = function() {
    if (!MaschineMK3.tempoVisible) { return; }
    // D1/D5: Sync
    MaschineMK3.setLed("d1", engine.getValue("[Channel1]", "sync_enabled") ? 63 : 16);
    MaschineMK3.setLed("d5", engine.getValue("[Channel2]", "sync_enabled") ? 63 : 16);
    // D2/D6: Keylock
    MaschineMK3.setLed("d2", engine.getValue("[Channel1]", "keylock") ? 63 : 16);
    MaschineMK3.setLed("d6", engine.getValue("[Channel2]", "keylock") ? 63 : 16);
    // D3/D7: Ramp active
    MaschineMK3.setLed("d3", MaschineMK3.tempoState.rampTimerA ? 63 : 16);
    MaschineMK3.setLed("d7", MaschineMK3.tempoState.rampTimerB ? 63 : 16);
    // D4/D8: Reset (always dim)
    MaschineMK3.setLed("d4", 16);
    MaschineMK3.setLed("d8", 16);
};
```

- [ ] **Step 2: Call updateTempoDButtonLEDs when tempo panel opens**

In `toggleTempoPanel()`, add after the `MaschineMK3.updatePanels()` call:

```javascript
    if (MaschineMK3.tempoVisible) {
        MaschineMK3.updateTempoDButtonLEDs();
    }
```

- [ ] **Step 3: Add keylock LED connections in init()**

In `init()`, after the sync-enabled connections, add keylock feedback:

```javascript
    engine.makeConnection("[Channel1]", "keylock", function(value) {
        if (MaschineMK3.tempoVisible) {
            MaschineMK3.setLed("d2", value ? 63 : 16);
        }
    });
    engine.makeConnection("[Channel2]", "keylock", function(value) {
        if (MaschineMK3.tempoVisible) {
            MaschineMK3.setLed("d6", value ? 63 : 16);
        }
    });
```

- [ ] **Step 4: Add TEMPO LED init**

In `init()`, after the existing LED initializations (around line 1704 area), add:

```javascript
    MaschineMK3.setLed("tempo", 0);
```

- [ ] **Step 5: Verify no syntax errors**

Run: `node -c mapping/Native-Instruments-Maschine-MK3.js`
Expected: no output (clean parse)

- [ ] **Step 6: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(tempo): add D-button LED feedback for tempo panel"
```

---

### Task 8: Add skin config keys and ramp indicator widgets

**Files:**
- Modify: `skin/MK3/skin.xml`

- [ ] **Step 1: Add new config keys to skin attributes**

In `skin.xml`, in the `<attributes>` section (around line 24, after `show_sidebar`), add:

```xml
      <attribute config_key="[Skin],show_tempo">0</attribute>
      <attribute config_key="[Skin],show_ramp_a">0</attribute>
      <attribute config_key="[Skin],show_ramp_b">0</attribute>
```

- [ ] **Step 2: Add ramp indicator to Deck A screen**

Find the `DeckStatusA` widget group (around line 190, the BPM and position section). Add a ramp indicator label inside the `DeckStatusA` children, after the `NumberBpm` widget:

```xml
            <Label>
              <ObjectName>RampIndicator</ObjectName>
              <Size>60f,14f</Size>
              <Text>RAMP&#x2192;B</Text>
              <Connection>
                <ConfigKey>[Skin],show_ramp_a</ConfigKey>
                <BindProperty>visible</BindProperty>
              </Connection>
            </Label>
```

- [ ] **Step 3: Add ramp indicator to Deck B screen**

Find the equivalent `DeckStatusB` section (around line 1581). Add the same indicator:

```xml
            <Label>
              <ObjectName>RampIndicator</ObjectName>
              <Size>60f,14f</Size>
              <Text>RAMP&#x2192;A</Text>
              <Connection>
                <ConfigKey>[Skin],show_ramp_b</ConfigKey>
                <BindProperty>visible</BindProperty>
              </Connection>
            </Label>
```

- [ ] **Step 4: Add RampIndicator style to style.qss**

In `skin/MK3/style.qss`, add:

```css
#RampIndicator {
  font-size: 10px;
  font-weight: bold;
  color: #88aaff;
  background-color: #222244;
  border-radius: 2px;
  padding: 1px 4px;
}
```

- [ ] **Step 5: Commit**

```bash
git add skin/MK3/skin.xml skin/MK3/style.qss
git commit -m "feat(tempo): add skin config keys and ramp indicators"
```

---

### Task 9: Add TempoPanel widgets to skin.xml

**Files:**
- Modify: `skin/MK3/skin.xml`

- [ ] **Step 1: Add TempoPanel for Deck A (left screen)**

After the existing `StemMixerPanel` widget group (search for `</WidgetGroup>` after the stem mixer section, around line 1111), add the Deck A tempo panel:

```xml
    <!-- ═══ TEMPO PANEL — DECK A (Left Screen) ═══ -->
    <WidgetGroup>
      <ObjectName>TempoPanelA</ObjectName>
      <Size>480,272</Size>
      <SizePolicy>f,f</SizePolicy>
      <Layout>vertical</Layout>
      <Connection>
        <ConfigKey>[Skin],show_tempo</ConfigKey>
        <BindProperty>visible</BindProperty>
      </Connection>
      <Children>

        <!-- D-button labels (top bar) -->
        <WidgetGroup>
          <ObjectName>TempoDButtonBar</ObjectName>
          <SizePolicy>me,f</SizePolicy>
          <Size>0,24</Size>
          <Layout>horizontal</Layout>
          <Children>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D1: SYNC</Text></Label>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D2: KEYLOCK</Text></Label>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D3: RAMP&#x2192;B</Text></Label>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D4: RESET</Text></Label>
          </Children>
        </WidgetGroup>

        <!-- Track info -->
        <WidgetGroup>
          <ObjectName>TempoTrackInfo</ObjectName>
          <SizePolicy>me,f</SizePolicy>
          <Size>0,20</Size>
          <Layout>horizontal</Layout>
          <Children>
            <Label><ObjectName>TempoDeckLabel</ObjectName><Size>60f,20f</Size><Text>DECK A</Text></Label>
            <TrackProperty>
              <ObjectName>TempoTrackTitle</ObjectName>
              <SizePolicy>me,f</SizePolicy>
              <Property>title</Property>
              <Channel>1</Channel>
            </TrackProperty>
          </Children>
        </WidgetGroup>

        <!-- BPM display (large) -->
        <WidgetGroup>
          <ObjectName>TempoBPMArea</ObjectName>
          <SizePolicy>me,me</SizePolicy>
          <Layout>vertical</Layout>
          <Children>
            <Label><ObjectName>TempoLabel</ObjectName><Size>0me,16f</Size><Text>TEMPO</Text></Label>
            <NumberBpm>
              <ObjectName>TempoBPMDisplay</ObjectName>
              <Channel>1</Channel>
              <SizePolicy>me,me</SizePolicy>
              <Connection>
                <ConfigKey>[Channel1],visual_bpm</ConfigKey>
              </Connection>
            </NumberBpm>
          </Children>
        </WidgetGroup>

        <!-- Knob labels (bottom) -->
        <WidgetGroup>
          <ObjectName>TempoKnobBar</ObjectName>
          <SizePolicy>me,f</SizePolicy>
          <Size>0,40</Size>
          <Layout>horizontal</Layout>
          <Children>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K1: TEMPO</Text></Label>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K2: KEY</Text></Label>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K3: &#x2014;</Text></Label>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K4: TARGET</Text></Label>
          </Children>
        </WidgetGroup>

      </Children>
    </WidgetGroup>
```

- [ ] **Step 2: Add TempoPanel for Deck B (right screen)**

After the Deck A tempo panel, add the Deck B version. This goes in the right screen area. Find the right screen section (after `<!-- ═══════ RIGHT SCREEN: DECK B (480x272) ═══════ -->`). Add a matching panel after the Deck B's stem mixer panel:

```xml
    <!-- ═══ TEMPO PANEL — DECK B (Right Screen) ═══ -->
    <WidgetGroup>
      <ObjectName>TempoPanelB</ObjectName>
      <Size>480,272</Size>
      <SizePolicy>f,f</SizePolicy>
      <Layout>vertical</Layout>
      <Connection>
        <ConfigKey>[Skin],show_tempo</ConfigKey>
        <BindProperty>visible</BindProperty>
      </Connection>
      <Children>

        <!-- D-button labels (top bar) -->
        <WidgetGroup>
          <ObjectName>TempoDButtonBar</ObjectName>
          <SizePolicy>me,f</SizePolicy>
          <Size>0,24</Size>
          <Layout>horizontal</Layout>
          <Children>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D5: SYNC</Text></Label>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D6: KEYLOCK</Text></Label>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D7: RAMP&#x2192;A</Text></Label>
            <Label><ObjectName>TempoDLabel</ObjectName><Size>120f,24f</Size><Text>D8: RESET</Text></Label>
          </Children>
        </WidgetGroup>

        <!-- Track info -->
        <WidgetGroup>
          <ObjectName>TempoTrackInfo</ObjectName>
          <SizePolicy>me,f</SizePolicy>
          <Size>0,20</Size>
          <Layout>horizontal</Layout>
          <Children>
            <Label><ObjectName>TempoDeckLabel</ObjectName><Size>60f,20f</Size><Text>DECK B</Text></Label>
            <TrackProperty>
              <ObjectName>TempoTrackTitle</ObjectName>
              <SizePolicy>me,f</SizePolicy>
              <Property>title</Property>
              <Channel>2</Channel>
            </TrackProperty>
          </Children>
        </WidgetGroup>

        <!-- BPM display (large) -->
        <WidgetGroup>
          <ObjectName>TempoBPMArea</ObjectName>
          <SizePolicy>me,me</SizePolicy>
          <Layout>vertical</Layout>
          <Children>
            <Label><ObjectName>TempoLabel</ObjectName><Size>0me,16f</Size><Text>TEMPO</Text></Label>
            <NumberBpm>
              <ObjectName>TempoBPMDisplay</ObjectName>
              <Channel>2</Channel>
              <SizePolicy>me,me</SizePolicy>
              <Connection>
                <ConfigKey>[Channel2],visual_bpm</ConfigKey>
              </Connection>
            </NumberBpm>
          </Children>
        </WidgetGroup>

        <!-- Knob labels (bottom) -->
        <WidgetGroup>
          <ObjectName>TempoKnobBar</ObjectName>
          <SizePolicy>me,f</SizePolicy>
          <Size>0,40</Size>
          <Layout>horizontal</Layout>
          <Children>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K5: TEMPO</Text></Label>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K6: KEY</Text></Label>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K7: &#x2014;</Text></Label>
            <Label><ObjectName>TempoKnobLabel</ObjectName><Size>120f,40f</Size><Text>K8: TARGET</Text></Label>
          </Children>
        </WidgetGroup>

      </Children>
    </WidgetGroup>
```

- [ ] **Step 3: Add tempo panel styles to style.qss**

In `skin/MK3/style.qss`, add:

```css
#TempoPanelA, #TempoPanelB {
  background-color: #1a1a2e;
}

#TempoDButtonBar {
  background-color: #252545;
  border-bottom: 1px solid #444444;
}

#TempoDLabel {
  font-size: 10px;
  color: #aaaaaa;
  qproperty-alignment: AlignCenter;
  border-right: 1px solid #333333;
}

#TempoTrackInfo {
  padding: 2px 8px;
}

#TempoDeckLabel {
  font-size: 11px;
  font-weight: bold;
  color: #88aaff;
}

#TempoTrackTitle {
  font-size: 11px;
  color: #aaaaaa;
}

#TempoBPMArea {
  qproperty-alignment: AlignCenter;
}

#TempoLabel {
  font-size: 11px;
  color: #888888;
  qproperty-alignment: AlignCenter;
  letter-spacing: 2px;
}

#TempoBPMDisplay {
  font-size: 48px;
  font-weight: bold;
  color: #ffffff;
  qproperty-alignment: AlignCenter;
}

#TempoKnobBar {
  border-top: 1px solid #333333;
}

#TempoKnobLabel {
  font-size: 10px;
  color: #888888;
  qproperty-alignment: AlignCenter;
}
```

- [ ] **Step 4: Commit**

```bash
git add skin/MK3/skin.xml skin/MK3/style.qss
git commit -m "feat(tempo): add tempo panel widgets and styles to skin"
```

---

### Task 10: Deploy and test on hardware

**Files:**
- No code changes — deployment and manual verification

- [ ] **Step 1: Copy mapping and skin to Pi**

```bash
scp mapping/Native-Instruments-Maschine-MK3.js mixxx-pi:~/.mixxx/controllers/
scp -r skin/MK3/ mixxx-pi:~/.mixxx/skins/
```

- [ ] **Step 2: Restart Mixxx on the Pi**

```bash
ssh mixxx-pi "killall mixxx; sleep 2; DISPLAY=:0 /usr/local/bin/mixxx &"
```

- [ ] **Step 3: Manual test checklist**

Verify each feature on hardware:

1. Press TEMPO button → both screens show tempo panel, TEMPO LED lights solid
2. Press TEMPO again → panel closes, deck screens restore, TEMPO LED off
3. Open mixer → tempo panel closes; open tempo → mixer closes (mutual exclusion)
4. Turn K1 → Deck A tempo adjusts
5. Turn K2 → Deck A key adjusts
6. Turn K4 → ramp target cycles (check screen label changes)
7. Press D1 → Deck A sync toggles, D1 LED reflects state
8. Press D2 → Deck A keylock toggles, D2 LED reflects state
9. Press D3 → ramp starts, D3 LED bright, TEMPO LED pulses
10. Press D3 again → ramp stops
11. Start ramp, close tempo panel → ramp continues, TEMPO LED pulses, deck screen shows "RAMP→B"
12. Load new track during ramp → ramp stops
13. Repeat tests for Deck B (K5-K8, D5-D8)

- [ ] **Step 4: Commit any fixes and final state**

```bash
git add -A
git commit -m "fix(tempo): hardware testing adjustments"
```

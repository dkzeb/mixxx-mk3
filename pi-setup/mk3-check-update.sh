#!/bin/bash
# Pre-boot update checker for MK3.
# Shows update prompt on the MK3 screens via Xvfb.
# Uses MK3 play button = "Update Now", any other = "Skip".
# Auto-skips after 30 seconds.
#
# Called from mixxx.service ExecStartPre.

set -uo pipefail

PROJECT_DIR="${MK3_PROJECT_DIR:-/home/$(whoami)/mixx-mk3}"
DISPLAY="${DISPLAY:-:99}"
export DISPLAY
TIMEOUT=30

cd "$PROJECT_DIR" || exit 0

# ── Check for updates ────────────────────────────────────────────────
git fetch origin master --quiet 2>/dev/null || exit 0

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/master 2>/dev/null)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "mk3-check-update: up to date"
    exit 0
fi

BEHIND=$(git rev-list HEAD..origin/master --count 2>/dev/null)
echo "mk3-check-update: $BEHIND update(s) available"

# ── Show prompt on MK3 screens ──────────────────────────────────────
# Light up play button (bright) and stop button (dim) as visual cue
# Report 0x80: play=byte42, stop=byte44
LEDCMD=$(printf '\x00%.0s' {1..63})
# Build a minimal LED update — we'll use the controller.send approach
# but since Mixxx isn't running yet, write directly to hidraw
HIDRAW=$(ls /dev/hidraw* 2>/dev/null | head -1)

# Show dialog via xmessage (lighter than zenity, no GTK deps)
RESULT=1
if command -v zenity &>/dev/null; then
    zenity --question \
        --title="MK3 Update" \
        --text="$BEHIND update(s) available.\n\nUpdate now?" \
        --ok-label="Update Now" \
        --cancel-label="Later" \
        --timeout=$TIMEOUT \
        --width=400 2>/dev/null
    RESULT=$?
elif command -v xmessage &>/dev/null; then
    xmessage -center -timeout $TIMEOUT \
        -buttons "Update Now:0,Later:1" \
        "$BEHIND update(s) available. Update now?"
    RESULT=$?
fi

# Result: 0 = Update Now, 1/5 = Later/Timeout
if [ "$RESULT" -eq 0 ]; then
    echo "mk3-check-update: updating..."

    # Show "Updating..." message
    if command -v zenity &>/dev/null; then
        zenity --info --text="Updating MK3...\nPlease wait." \
            --no-wrap --timeout=60 --width=400 2>/dev/null &
        ZPID=$!
    fi

    git pull --ff-only origin master 2>&1 | tail -5
    bash "$PROJECT_DIR/pi-setup/mk3-update.sh" --no-restart 2>&1 | tail -10

    # Kill the "Updating..." dialog
    kill $ZPID 2>/dev/null
    wait $ZPID 2>/dev/null

    echo "mk3-check-update: update complete"
else
    echo "mk3-check-update: skipped"
fi

exit 0

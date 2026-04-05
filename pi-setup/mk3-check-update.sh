#!/bin/bash
# Pre-boot update checker for MK3.
# Shows update prompt on MK3 screens, uses MK3 buttons for input.
# play = "Update Now", stop = "Later", auto-skips after 30s.
#
# Called from mixxx.service ExecStartPre.

set -uo pipefail

PROJECT_DIR="${MK3_PROJECT_DIR:-/home/$(whoami)/mixxx-mk3}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

# ── Start MK3 button reader (translates play/stop to Enter/Escape) ──
python3 "$SCRIPT_DIR/mk3-button-reader.py" &
READER_PID=$!

# ── Show dialog on MK3 screens ──────────────────────────────────────
RESULT=1
# Position zenity on left MK3 screen (480x272, origin 0,0)
move_to_left_screen() {
    for _ in $(seq 1 20); do
        WID=$(xdotool search --name "$1" 2>/dev/null | head -1)
        if [ -n "$WID" ]; then
            xdotool windowmove "$WID" 0 0 2>/dev/null
            xdotool windowsize "$WID" 480 272 2>/dev/null
            return
        fi
        sleep 0.1
    done
}
if command -v zenity &>/dev/null; then
    move_to_left_screen "MK3 Update" &
    zenity --question \
        --title="MK3 Update" \
        --text="$BEHIND update(s) available.\n\nPress PLAY to update, STOP to skip." \
        --ok-label="Update Now [PLAY]" \
        --cancel-label="Later [STOP]" \
        --timeout=$TIMEOUT \
        --width=480 2>/dev/null
    RESULT=$?
fi

# ── Stop button reader ──────────────────────────────────────────────
kill $READER_PID 2>/dev/null
wait $READER_PID 2>/dev/null

# Result: 0 = Update Now, 1 = Later, 5 = Timeout
if [ "$RESULT" -eq 0 ]; then
    echo "mk3-check-update: updating..."

    # Show progress message on left screen
    move_to_left_screen "Updating" &
    zenity --info --text="Updating MK3...\nPlease wait." \
        --title="Updating" \
        --no-wrap --timeout=120 --width=480 2>/dev/null &
    ZPID=$!

    git pull --ff-only origin master 2>&1 | tail -5

    # Run update without restarting Mixxx (we're in ExecStartPre)
    bash "$PROJECT_DIR/pi-setup/mk3-update.sh" --no-restart 2>&1 | tail -10

    kill $ZPID 2>/dev/null
    wait $ZPID 2>/dev/null

    echo "mk3-check-update: update complete"
else
    echo "mk3-check-update: skipped (result=$RESULT)"
fi

exit 0

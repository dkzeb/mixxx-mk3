#!/bin/bash
set -euo pipefail

# MK3 Boot Splash
# Left screen:  animated GIF logo (boomerang loop)
# Right screen: live boot log output
# Stopped automatically when mk3-screen-daemon takes over.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SPLASH_GIF="$SCRIPT_DIR/bootsplash-left-anim.gif"
SPLASH_PNG="$SCRIPT_DIR/bootsplash-left.png"
MK3="/usr/local/bin/mk3"

WIDTH=480
HEIGHT=272
FRAME_DIR=""

cleanup() {
    [ -n "$FRAME_DIR" ] && rm -rf "$FRAME_DIR"
    exit 0
}
trap cleanup SIGTERM SIGINT EXIT

# ── Extract GIF frames to raw RGB565 ─────────────────────────────────
FRAME_DIR=$(mktemp -d)
FRAMES=()

if [ -f "$SPLASH_GIF" ]; then
    # Extract all GIF frames as a single raw RGB565 stream, then split per frame
    ffmpeg -v quiet -i "$SPLASH_GIF" -pix_fmt rgb565le -s ${WIDTH}x${HEIGHT} \
        -f rawvideo "$FRAME_DIR/all_frames.raw" 2>/dev/null || true

    FRAME_BYTES=$((WIDTH * HEIGHT * 2))
    if [ -f "$FRAME_DIR/all_frames.raw" ]; then
        FILE_SIZE=$(stat -c%s "$FRAME_DIR/all_frames.raw")
        NFRAMES=$((FILE_SIZE / FRAME_BYTES))
        for ((i = 0; i < NFRAMES; i++)); do
            dd if="$FRAME_DIR/all_frames.raw" of="$FRAME_DIR/frame_${i}.raw" \
                bs=$FRAME_BYTES skip=$i count=1 2>/dev/null
            FRAMES+=("$FRAME_DIR/frame_${i}.raw")
        done
        rm -f "$FRAME_DIR/all_frames.raw"
    fi
elif [ -f "$SPLASH_PNG" ]; then
    # Fallback: static PNG as single frame
    ffmpeg -v quiet -i "$SPLASH_PNG" -pix_fmt rgb565le -s ${WIDTH}x${HEIGHT} \
        -f rawvideo "$FRAME_DIR/frame_0.raw" 2>/dev/null || true
    [ -f "$FRAME_DIR/frame_0.raw" ] && FRAMES+=("$FRAME_DIR/frame_0.raw")
fi

NFRAMES=${#FRAMES[@]}
if [ "$NFRAMES" -eq 0 ]; then
    echo "No splash frames found" >&2
    exit 1
fi

# ── Build boomerang sequence: 0 1 2 ... N-1 N-2 ... 1 ────────────────
SEQ=()
for ((i = 0; i < NFRAMES; i++)); do
    SEQ+=("$i")
done
for ((i = NFRAMES - 2; i >= 1; i--)); do
    SEQ+=("$i")
done
SEQ_LEN=${#SEQ[@]}

# ── Main loop: alternate left animation + right boot log ─────────────
frame_idx=0
tick=0
LOG_INTERVAL=5  # update boot log every N animation frames

while true; do
    # Left screen: next animation frame
    cat "${FRAMES[${SEQ[$frame_idx]}]}" | "$MK3" --pipe --target left 2>/dev/null || true
    frame_idx=$(( (frame_idx + 1) % SEQ_LEN ))

    # Right screen: boot log (every LOG_INTERVAL frames to prioritise animation)
    tick=$(( (tick + 1) % LOG_INTERVAL ))
    if [ "$tick" -eq 0 ]; then
        LINES=$(journalctl -b --no-pager -o cat -n 16 2>/dev/null || echo "Booting...")
        "$MK3" --text "$LINES" --target right --font-size 13 --mono --color 00C880 2>/dev/null || true
    fi
done

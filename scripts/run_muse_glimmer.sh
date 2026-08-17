#!/usr/bin/env bash
# ==============================================================================
# Muse-Glimmer-30B Local Server Launcher for Mac M5 Pro (Metal Acceleration)
# ==============================================================================
# Model: Muse-Glimmer-30B-GGUF (~16.8GB) + mmproj (~1.4GB) + dflash (~1.6GB)
# Memory Footprint: Fits comfortably in 24GB Unified Memory with 32k/64k Context
# ==============================================================================

set -euo pipefail

MODEL_DIR="${MODEL_DIR:-llama/runtime/models/Muse-Glimmer-30B}"
MAIN_MODEL="${MAIN_MODEL:-$MODEL_DIR/muse-glimmer-30B-kquant-17gb.gguf}"
MMPROJ_MODEL="${MMPROJ_MODEL:-$MODEL_DIR/mmproj-kquant.gguf}"
DFLASH_MODEL="${DFLASH_MODEL:-$MODEL_DIR/dflash-kquant.gguf}"

CONTEXT_SIZE="${CONTEXT_SIZE:-32768}"
SLOTS="${SLOTS:-1}"
PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"

echo "========================================================"
echo "🧠 Launching Muse-Glimmer-30B on llama-server (Metal)"
echo "========================================================"
echo "  Main Model:    $MAIN_MODEL"
echo "  Vision mmproj: $MMPROJ_MODEL"
echo "  Drafter Model: $DFLASH_MODEL"
echo "  Context Size:  $CONTEXT_SIZE"
echo "  Slots:         $SLOTS (dedicated single agent task)"
echo "  Endpoint:      http://$HOST:$PORT/v1"
echo "========================================================"

# Check if llama-server is installed
if ! command -v llama-server &> /dev/null; then
    echo "⚠️ 'llama-server' binary not found on PATH."
    echo "Install llama.cpp with Metal support: 'brew install llama.cpp' or build from source."
    exit 1
fi

# Build arguments dynamically based on available files
ARGS=(
    "-m" "$MAIN_MODEL"
    "-c" "$CONTEXT_SIZE"
    "-ngl" "99"
    "-np" "$SLOTS"
    "--port" "$PORT"
    "--host" "$HOST"
    "--cont-batching"
)

# Attach vision projector if present
if [ -f "$MMPROJ_MODEL" ]; then
    echo "👁️  Enabling multimodal vision projector: $MMPROJ_MODEL"
    ARGS+=("--mmproj" "$MMPROJ_MODEL")
else
    echo "ℹ️  Vision projector not found at $MMPROJ_MODEL. Running in text-only mode."
fi

# Attach speculative drafter if present
if [ -f "$DFLASH_MODEL" ]; then
    echo "⚡ Enabling speculative decoding with drafter: $DFLASH_MODEL"
    ARGS+=("-md" "$DFLASH_MODEL" "--draft-max" "16")
fi

echo "🚀 Starting server..."
exec llama-server "${ARGS[@]}"

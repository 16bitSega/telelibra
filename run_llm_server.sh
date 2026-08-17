#!/usr/bin/env bash
# ==============================================================================
# Muse-Glimmer-30B Local Server Launcher for Mac M5 Pro (Metal Acceleration)
# ==============================================================================
# Model: Muse-Glimmer-30B-GGUF (~16.8GB) + mmproj (~1.4GB) + dflash (~1.6GB)
# Context: 32,768 (32k tokens) | Slots: 1 (-np 1)
# Memory Profile: ~20.5 GB in Unified Memory (Tuned for 24GB Mac M5 Pro)
# ==============================================================================

set -euo pipefail

# 1. Resolve Model Directory (searches current dir, parent dir, or env var)
MODEL_DIR="${MODEL_DIR:-}"

if [ -z "$MODEL_DIR" ]; then
    if [ -d "llama/runtime/models/Muse-Glimmer-30B" ]; then
        MODEL_DIR="llama/runtime/models/Muse-Glimmer-30B"
    elif [ -d "../microlize/llama/runtime/models/Muse-Glimmer-30B" ]; then
        MODEL_DIR="../microlize/llama/runtime/models/Muse-Glimmer-30B"
    else
        MODEL_DIR="llama/runtime/models/Muse-Glimmer-30B"
    fi
fi

MAIN_MODEL="${MAIN_MODEL:-$MODEL_DIR/muse-glimmer-30B-kquant-17gb.gguf}"
MMPROJ_MODEL="${MMPROJ_MODEL:-$MODEL_DIR/mmproj-kquant.gguf}"
DFLASH_MODEL="${DFLASH_MODEL:-$MODEL_DIR/dflash-kquant.gguf}"

CONTEXT_SIZE="${CONTEXT_SIZE:-16384}"
SLOTS="${SLOTS:-1}"
PORT="${PORT:-8080}"
HOST="${HOST:-127.0.0.1}"

echo "========================================================================"
echo "🧠 LAUNCHING MUSE-GLIMMER-30B ON METAL (llama.cpp)"
echo "========================================================================"
echo "  • Model Directory:     $MODEL_DIR"
echo "  • Main Model (30B):    $MAIN_MODEL"
echo "  • Vision Projector:    $MMPROJ_MODEL"
echo "  • Context Window:      $CONTEXT_SIZE (16k tokens, optimized for 24GB RAM)"
echo "  • KV Cache Quant:      Q8_0 (50% memory savings)"
echo "  • Slots Allocation:    $SLOTS (dedicated single agent task)"
echo "  • Endpoint URL:        http://localhost:$PORT/v1"
echo "========================================================================"

# 2. Find llama-server binary (prioritizing Homebrew installation)
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-}"
CANDIDATE_PATHS=(
    "$LLAMA_SERVER_BIN"
    "/opt/homebrew/bin/llama-server"
    "$(which llama-server 2>/dev/null || true)"
    "$HOME/llama.cpp/build/bin/llama-server"
    "$HOME/llama.cpp/llama-server"
    "/usr/local/bin/llama-server"
    "../microlize/llama/runtime/bin/llama-server"
    "llama/runtime/bin/llama-server"
)

for p in "${CANDIDATE_PATHS[@]}"; do
    if [ -n "$p" ] && [ -x "$p" ]; then
        LLAMA_SERVER_BIN="$p"
        break
    fi
done

if [ -z "$LLAMA_SERVER_BIN" ]; then
    echo "⚠️  'llama-server' binary not found automatically."
    echo "Please ensure llama.cpp is built or installed on PATH."
    exit 1
fi

echo "🔍 Using binary: $LLAMA_SERVER_BIN"

# 3. Build server arguments optimized for 24GB Unified Memory
ARGS=(
    "-m" "$MAIN_MODEL"
    "-c" "$CONTEXT_SIZE"
    "-ngl" "99"
    "-np" "$SLOTS"
    "--port" "$PORT"
    "--host" "$HOST"
    "-ctk" "q8_0"
    "-ctv" "q8_0"
    "-b" "512"
    "-ub" "256"
    "--cont-batching"
    "--reasoning-preserve"
)

# 4. Attach Vision Projector (mmproj)
if [ -f "$MMPROJ_MODEL" ]; then
    echo "👁️  Attaching Multimodal Vision Projector: $MMPROJ_MODEL"
    ARGS+=("--mmproj" "$MMPROJ_MODEL")
else
    echo "ℹ️  Vision projector not found at $MMPROJ_MODEL (will run text-only mode)."
fi

# 5. Speculative Drafter (dflash) - opt-in via ENABLE_DFLASH=true
ENABLE_DFLASH="${ENABLE_DFLASH:-false}"
if [ "$ENABLE_DFLASH" = "true" ] && [ -f "$DFLASH_MODEL" ]; then
    echo "⚡ Attaching Speculative Drafter: $DFLASH_MODEL"
    ARGS+=("-md" "$DFLASH_MODEL" "--spec-draft-n-max" "8")
else
    echo "🛡️  Running stable primary inference without drafter (prevents Metal OOM on 24GB)."
fi

echo "🚀 Starting llama-server on Metal..."
echo "------------------------------------------------------------------------"
exec "$LLAMA_SERVER_BIN" "${ARGS[@]}"

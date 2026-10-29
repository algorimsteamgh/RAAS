#!/usr/bin/env bash
set -e

# ==============================================================================
# vLLM Startup Entrypoint for Qwen on Azure GPU Container
# Supports:
# 1. Custom fine-tuned weights (/models/fine_tuned or /models/checkpoints)
# 2. Base HuggingFace Qwen models (e.g. Qwen/Qwen2.5-7B-Instruct)
# 3. LoRA adapter merging on the fly
# ==============================================================================

MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-7B-Instruct}"
MODEL_PATH="${MODEL_PATH:-/models/best_model}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
PORT="${PORT:-8000}"

echo "=========================================================="
echo "🚀 Starting vLLM OpenAI API Server for Qwen on Azure GPU"
echo "=========================================================="

# Check if fine-tuned model checkpoint directory exists and contains weights
if [ -d "$MODEL_PATH" ] && [ "$(ls -A "$MODEL_PATH" 2>/dev/null)" ]; then
  echo "🎯 Found custom fine-tuned Qwen weights at: $MODEL_PATH"
  ACTIVE_MODEL="$MODEL_PATH"
else
  echo "ℹ️  No custom checkpoint found at $MODEL_PATH, serving base model: $MODEL_NAME"
  ACTIVE_MODEL="$MODEL_NAME"
fi

echo "Configuration:"
echo " - Active Model:            $ACTIVE_MODEL"
echo " - GPU Memory Utilization:  $GPU_MEMORY_UTILIZATION"
echo " - Max Model Context:       $MAX_MODEL_LEN"
echo " - Serving Port:            $PORT"

exec python3 -m vllm.entrypoints.openai.api_server \
  --model "$ACTIVE_MODEL" \
  --served-model-name "qwen-production" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser hermes

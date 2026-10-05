#!/usr/bin/env bash
# serve-gemma4.sh -- Launch vLLM serving Gemma 4 31B for SDG pipeline teacher model
#
# Starts a vLLM OpenAI-compatible API server with Gemma 4 31B-IT, configured
# for native tool-call parsing using vLLM's gemma4 parser. The server exposes
# an OpenAI-compatible /v1/chat/completions endpoint that sdg_hub's LLMChatBlock
# calls via the LiteLLM "hosted_vllm/" provider prefix.
#
# Usage: sdg/scripts/serve-gemma4.sh [--fp8] [--tp N]
#   --fp8  : Enable FP8 quantization (halves VRAM: ~31GB vs ~62GB for BF16)
#   --tp N : Set tensor-parallel size (e.g., --tp 2 for 2x A100 40GB)
#
# Requires:
#   - vllm >= 0.31.0 (native gemma4 tool-call parser)
#   - GPU with >= 62GB VRAM (BF16) or >= 31GB (FP8)
#   - Model weights downloaded or accessible via HuggingFace Hub
#
# Environment variables (all optional, defaults shown):
#   MODEL            google/gemma-4-31B-it
#   DTYPE            bfloat16
#   MAX_MODEL_LEN    8192
#   GPU_MEM_UTIL     0.90
#   PORT             8000
#
# References:
#   - D-08: Gemma 4 31B dense as teacher model
#   - D-09: vLLM --enable-auto-tool-choice --tool-call-parser gemma4
#   - D-10: GPU access already available on separate RHOAI cluster
#   - Pitfall 3: --max-num-seqs mitigates concurrent pad-token bug

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

MODEL="${MODEL:-google/gemma-4-31B-it}"
DTYPE="${DTYPE:-bfloat16}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.90}"
PORT="${PORT:-8000}"
VLLM_QUANTIZATION="${VLLM_QUANTIZATION:-}"
VLLM_TP_SIZE="${VLLM_TP_SIZE:-1}"

# Note: vLLM bundles the Gemma 4 chat template at
# examples/tool_chat_template_gemma4.jinja in the vLLM source tree.
# When running from a pip install, vLLM discovers this automatically
# via the model's tokenizer_config.json chat_template field.
CHAT_TEMPLATE="${CHAT_TEMPLATE:-}"

# ─── Argument Parsing ────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fp8)
      VLLM_QUANTIZATION="fp8"
      DTYPE="float16"
      shift
      ;;
    --tp)
      VLLM_TP_SIZE="${2:?'--tp requires a numeric argument (e.g., --tp 2)'}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--fp8] [--tp N]"
      echo "  --fp8  : Enable FP8 quantization (halves VRAM requirement)"
      echo "  --tp N : Tensor-parallel size (e.g., 2 for 2x GPU)"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument '$1'. Use --help for usage."
      exit 1
      ;;
  esac
done

# ─── Build vLLM Command ─────────────────────────────────────────────────────

CMD=(
  vllm serve "$MODEL"
  --dtype "$DTYPE"
  --max-model-len "$MAX_MODEL_LEN"
  --gpu-memory-utilization "$GPU_MEM_UTIL"
  --enable-auto-tool-choice
  --tool-call-parser gemma4
  --reasoning-parser gemma4
  --port "$PORT"
  --host 0.0.0.0
  --max-num-seqs 64
)

# Add quantization only when specified (FP8)
if [[ -n "$VLLM_QUANTIZATION" ]]; then
  CMD+=(--quantization "$VLLM_QUANTIZATION")
fi

# Add tensor-parallel size only when >1
if [[ "$VLLM_TP_SIZE" -gt 1 ]]; then
  CMD+=(--tensor-parallel-size "$VLLM_TP_SIZE")
fi

# Add explicit chat template only when specified
if [[ -n "$CHAT_TEMPLATE" ]]; then
  CMD+=(--chat-template "$CHAT_TEMPLATE")
fi

# ─── Launch ──────────────────────────────────────────────────────────────────

echo "=== vLLM Gemma 4 31B Teacher Model ==="
echo "Model:           $MODEL"
echo "Dtype:           $DTYPE"
echo "Max model len:   $MAX_MODEL_LEN"
echo "GPU mem util:    $GPU_MEM_UTIL"
echo "Port:            $PORT"
echo "Tool-call parser: gemma4"
echo "Max num seqs:    64 (Pitfall 3 mitigation)"
[[ -n "$VLLM_QUANTIZATION" ]] && echo "Quantization:    $VLLM_QUANTIZATION"
[[ "$VLLM_TP_SIZE" -gt 1 ]] && echo "Tensor parallel: $VLLM_TP_SIZE"
echo ""
echo "Command: ${CMD[*]}"
echo ""

exec "${CMD[@]}"

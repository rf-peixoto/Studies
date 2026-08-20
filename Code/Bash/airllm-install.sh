#!/usr/bin/env bash
#
# run_airllm_qwen38.sh
# --------------------
# Creates a Python venv, installs AirLLM (https://github.com/lyogavin/airllm),
# downloads huihui-ai/Huihui-Qwen3.8-27B-abliterated, and runs one benign prompt
# to confirm the model loads and generates.
#
# AirLLM streams the model one layer at a time, so VRAM need is small (~1-3 GB),
# but DISK is the real constraint: it downloads the full checkpoint (~56 GB) and
# then writes a layer-split copy. Budget ~110 GB, or set AIRLLM_DELETE_ORIGINAL=1
# to drop the original after splitting (~56 GB).
#
# Usage:
#   ./run_airllm_qwen38.sh
#
# Optional environment overrides:
#   VENV_DIR=airllm-venv           # where to create the virtualenv
#   PROMPT="What is 2+2?"          # the validation prompt
#   MAX_NEW_TOKENS=32              # tokens to generate for the smoke test
#   HF_TOKEN=hf_xxx                # only if you hit a gated/rate-limited download
#   AIRLLM_DELETE_ORIGINAL=1       # delete the raw HF download after layer-splitting
#
set -euo pipefail

MODEL_ID="huihui-ai/Huihui-Qwen3.8-27B-abliterated"
VENV_DIR="${VENV_DIR:-airllm-venv}"
PROMPT="${PROMPT:-Hello}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-32}"
AIRLLM_DELETE_ORIGINAL="${AIRLLM_DELETE_ORIGINAL:-0}"

echo "=================================================================="
echo " AirLLM validation run"
echo "   model : ${MODEL_ID}"
echo "   venv  : ${VENV_DIR}"
echo "   prompt: ${PROMPT}"
echo "=================================================================="
echo
echo "NOTE: this is a ~28B model. AirLLM will download ~56 GB and then write"
echo "      a layer-split copy. Make sure you have the disk space (see header)."
echo

# --- 1. Create and activate the virtual environment ---------------------------
if [ ! -d "${VENV_DIR}" ]; then
    echo "[1/4] Creating virtualenv at ${VENV_DIR} ..."
    python3 -m venv "${VENV_DIR}"
else
    echo "[1/4] Reusing existing virtualenv at ${VENV_DIR} ..."
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --quiet --upgrade pip wheel

# --- 2. Install dependencies --------------------------------------------------
# airllm pulls torch/accelerate. We pin transformers >=5.8 because the in-tree
# Qwen3_5ForConditionalGeneration class (this model's architecture) requires it,
# and airllm itself caps it at <5.13.
echo "[2/4] Installing airllm + dependencies (this can take a while) ..."
python -m pip install --quiet "airllm>=3.2.0"
python -m pip install --quiet "transformers>=5.8,<5.13"
python -m pip install --quiet "huggingface_hub[hf_transfer]"

# If your machine has a specific CUDA toolkit, you may want a matching torch build
# instead of the default PyPI wheel, e.g.:
#   pip install torch --index-url https://download.pytorch.org/whl/cu124

# --- 3. Download the model ----------------------------------------------------
# Populate the HF cache up front so the download is a distinct, resumable step.
# AirLLM will then reuse this cache (no second download) when it splits layers.
echo "[3/4] Downloading ${MODEL_ID} ..."
export HF_HUB_ENABLE_HF_TRANSFER=1
python - "$MODEL_ID" <<'PY'
import sys
from huggingface_hub import snapshot_download
model_id = sys.argv[1]
# Text-only smoke test: skip the GGUF quants if any, grab the safetensors weights.
path = snapshot_download(
    model_id,
    allow_patterns=["*.safetensors", "*.json", "*.txt", "tokenizer*", "*.model"],
)
print(f"Downloaded to: {path}")
PY

# --- 4. Load with AirLLM and run the validation prompt ------------------------
echo "[4/4] Loading with AirLLM and running the prompt ..."
AIRLLM_DELETE_ORIGINAL="${AIRLLM_DELETE_ORIGINAL}" \
MODEL_ID="${MODEL_ID}" \
PROMPT="${PROMPT}" \
MAX_NEW_TOKENS="${MAX_NEW_TOKENS}" \
HF_TOKEN="${HF_TOKEN:-}" \
python - <<'PY'
import os
import torch
from airllm import AutoModel

model_id        = os.environ["MODEL_ID"]
prompt          = os.environ["PROMPT"]
max_new_tokens  = int(os.environ["MAX_NEW_TOKENS"])
delete_original = os.environ.get("AIRLLM_DELETE_ORIGINAL", "0") == "1"
hf_token        = os.environ.get("HF_TOKEN") or None

device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Torch sees CUDA: {torch.cuda.is_available()} -> using device '{device}'")
if device == "cpu":
    print("WARNING: no GPU detected. This will work but be slow.")

# AirLLM splits the checkpoint layer-by-layer on first load; expect extra disk use.
kwargs = dict(device=device, delete_original=delete_original)
if hf_token:
    kwargs["hf_token"] = hf_token

print("Loading model (first run also splits layers to disk) ...")
model = AutoModel.from_pretrained(model_id, **kwargs)

# Format the prompt with the model's chat template (it's an instruct model).
messages = [{"role": "user", "content": prompt}]
try:
    # enable_thinking=False keeps the smoke test short (Qwen3.x reasoning toggle).
    text = model.tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
except TypeError:
    text = model.tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

inputs = model.tokenizer(
    text,
    return_tensors="pt",
    return_attention_mask=False,
    truncation=True,
    max_length=256,
    padding=False,
)
input_ids = inputs["input_ids"].to(device)

print("Generating ...")
generation_output = model.generate(
    input_ids,
    max_new_tokens=max_new_tokens,
    use_cache=True,
    return_dict_in_generate=True,
)

full   = model.tokenizer.decode(generation_output.sequences[0], skip_special_tokens=True)
answer = model.tokenizer.decode(
    generation_output.sequences[0][input_ids.shape[-1]:], skip_special_tokens=True
)

print("\n================ MODEL OUTPUT ================")
print("Prompt :", prompt)
print("Answer :", answer.strip())
print("---------- full decoded sequence ------------")
print(full.strip())
print("=============================================")
print("\nValidation complete: the model loaded and generated tokens successfully.")
PY

echo
echo "Done. Re-run any time with:  source ${VENV_DIR}/bin/activate && ./run_airllm_qwen38.sh"

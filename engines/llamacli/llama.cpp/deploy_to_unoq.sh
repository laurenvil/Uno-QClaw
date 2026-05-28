#!/bin/bash

# Force Python to look in your local user directory for the pip packages
export PYTHONPATH="$HOME/.local/lib/python3.10/site-packages:$PYTHONPATH"
PYTHON_CMD="python3.10"

# Target the specific Hugging Face cache directory
REPO_NAME="HuggingFaceTB--SmolLM2-135M-Instruct"
HF_CACHE_DIR="$HOME/.cache/huggingface/hub/models--${REPO_NAME}/snapshots"

# Automatically find the latest downloaded snapshot folder
HF_MODEL_PATH=$(find "$HF_CACHE_DIR" -mindepth 1 -maxdepth 1 -type d -print | head -n 1)
GGUF_OUT_DIR="./models/gguf_out"
UNOQ_IP="192.168.10.68"

mkdir -p $GGUF_OUT_DIR

echo "--- Step 1: Converting HF to GGUF (FP16) from HF Cache ---"
echo "Reading from: $HF_MODEL_PATH"
$PYTHON_CMD convert_hf_to_gguf.py "$HF_MODEL_PATH" --outfile "$GGUF_OUT_DIR/base.gguf"

echo "--- Step 2: Quantizing to Adreno-Optimized Q4_0 ---"
./build/bin/llama-quantize --pure "$GGUF_OUT_DIR/base.gguf" "$GGUF_OUT_DIR/unoq_optimized.gguf" Q4_0

echo "--- Step 3: Transferring to Uno Q ---"
ssh arduino@$UNOQ_IP "mkdir -p ~/models"
scp "$GGUF_OUT_DIR/unoq_optimized.gguf" arduino@$UNOQ_IP:~/models/

echo "Done! Run it on Uno Q using llama-cli with -ngl 99"
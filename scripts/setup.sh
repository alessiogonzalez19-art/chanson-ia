#!/bin/bash
# =============================================================
# Studio IA — Development Setup Script
# Run this once to prepare your environment
# =============================================================

set -e

echo "🚀 Studio IA — Setup"
echo "=================================================="

# ── 1. Check Python version ──────────────────────────────────
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "🐍 Python: $PYTHON_VERSION"

PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 10 ]; then
    echo "❌ Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi

# ── 2. Create virtual environment ────────────────────────────
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "✅ Virtual environment already exists"
fi

source venv/bin/activate

# ── 3. Upgrade pip ───────────────────────────────────────────
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet

# ── 4. Install PyTorch with CUDA ─────────────────────────────
echo "🔥 Installing PyTorch (CUDA 12.1)..."
pip install torch torchaudio \
    --index-url https://download.pytorch.org/whl/cu121 --quiet

# ── 5. Install project requirements ──────────────────────────
echo "📦 Installing requirements..."
pip install -r requirements.txt --quiet

# ── 6. Create directory structure ────────────────────────────
echo "📁 Creating workspace directories..."
python3 -c "from config import config; config.setup_directories()"

# ── 7. Check GPU availability ────────────────────────────────
echo ""
echo "🖥️  Hardware Check:"
python3 -c "
import torch
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    vram = props.total_memory / 1e9
    print(f'  ✅ GPU: {props.name} ({vram:.1f} GB VRAM)')
    if vram >= 24:
        print('  ✅ Sufficient VRAM for all world-class models')
    elif vram >= 12:
        print('  ⚠️  Limited VRAM — 4-bit quantization will be used')
    else:
        print('  ❌ VRAM too low (<12GB) — CPU fallback will be slow')
else:
    print('  ⚠️  No GPU detected — running in CPU mode (very slow)')
"

# ── 8. Frontend setup ─────────────────────────────────────────
if [ -d "frontend" ]; then
    echo ""
    echo "🎨 Setting up frontend..."
    cd frontend
    if [ ! -f "package.json" ]; then
        echo "  ⚠️  No package.json found in frontend/, skipping npm install"
    else
        npm install --silent
        echo "  ✅ Frontend dependencies installed"
    fi
    cd ..
fi

# ── 9. Done ───────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Download models: python scripts/download_models.py --all"
echo "  2. Start services:  bash scripts/start_dev.sh"
echo "  3. Open API docs:   http://localhost:8000/docs"
echo "=================================================="

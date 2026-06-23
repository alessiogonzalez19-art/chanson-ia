# 🎹 Studio IA Local et Autonome

**World-Class AI Music Production Studio with 10 Specialized Agents**

## 🏆 Best Open-Source Models Only

| Category | Model | Quality Level |
|----------|-------|---------------|
| 🧠 Orchestration | DeepSeek V3 (671B) | GPT-4 Class |
| 🎵 Music Generation | Stable Audio 2.0 | Commercial Grade |
| 🎤 Speech | Whisper Large V3 | State-of-the-Art |
| 🎚️ Separation | Demucs HT | Best SDR Scores |
| 🎛️ Mastering | Matchering 2.0 | Reference Quality |

## 🚀 Quick Start

### Prerequisites
- NVIDIA GPU with 24GB+ VRAM (RTX 4090 recommended)
- 64GB RAM minimum
- Python 3.10+
- CUDA 12.1+

### Installation

```bash
# Clone repository
git clone https://github.com/studio-ia-local/studio-ia.git
cd studio-ia

# Run setup
chmod +x scripts/setup.sh
./scripts/setup.sh

# Download models (70GB+)
python scripts/download_models.py --all

# Start services
./scripts/start_dev.sh
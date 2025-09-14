# 🐭 pyMiceTracking Panel

A comprehensive mouse tracking application with Panel interface and YOLO-based computer vision for behavioral analysis.

## 🚀 Features

- **Camera & Recording**: Live camera feed integration and recording
- **Animal Tracking**: YOLO-based mouse detection and tracking with GPU acceleration  
- **Ethological Analysis**: 
  - Video tracking analysis with heatmaps and info panels
  - Movement heatmap analysis with center of mass calculations
  - Individual plot generation and complete analysis panels
  - High-quality PNG/EPS export capabilities
- **IRL Analysis**: Real-world experiment integration
- **Synthetic Data**: Synthetic data generation tools
- **Extra Tools**: Additional utilities and GPU testing

## Prerequisites

- **Python**: ≥3.11
- **Package Manager**: [UV](https://docs.astral.sh/uv/) (recommended) or pip
- **GPU**: CUDA-compatible GPU recommended for optimal performance
- **System**: Linux/Windows/macOS

## 🏗️ Project Structure

```
proj-pymicetracking-panel/
├── 📄 pyproject.toml           # Project configuration (optimized)
├── 📄 readme.md               # This documentation
├── 📄 .gitignore             # Git ignored files
│
├── 📁 src/                   # Source code (professional layout)
│   └── 📁 pymicetracking_panel/
│       ├── 📄 __init__.py        # Package initialization  
│       ├── 📄 main.py           # Main application entry point
│       │
│       ├── 📁 camera_tab/       # Camera & Recording module
│       ├── 📁 tracking_tab/     # Animal Tracking module
│       │   ├── 📁 processing/   # Detection and tracking logic
│       │   ├── 📁 models/       # YOLO model files
│       │   └── 📁 temp/         # Temporary processing files
│       │
│       ├── 📁 ethological_tab/  # Ethological Analysis module  
│       │   ├── 📄 ethological_tab.py   # Main analysis interface
│       │   ├── 📄 testVideo_json.py    # Video processing utilities
│       │   └── 📁 temp/                # Analysis output files
│       │
│       ├── 📁 irl_tab/          # IRL Analysis module
│       ├── 📁 synthetic_tab/    # Synthetic Data module  
│       └── 📁 extra_tools_tab/  # Extra Tools module
│
├── 📁 tests/                 # Unit tests
├── 📁 experiments/          # Experiment data (gitignored)
└── 📁 models/               # Additional models
```

## ⚡ Quick Start

### Using UV (Recommended)

1. **Install UV** (if not already installed):

    **For Linux/MacOS**
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
    **For Windows**
    ```bash
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

3. **Clone and setup**:
   ```bash
   git clone https://github.com/heltonmaia/proj-pymicetracking-panel.git
   cd proj-pymicetracking-panel
   ```

4. **Install dependencies**:

   **For CPU-only installation** (works on all platforms):
   ```bash
   uv sync
   ```

   **For GPU acceleration** (Linux/Windows with NVIDIA GPU):
   ```bash
   # Install PyTorch with CUDA support first
   uv add "torch[cuda]" "torchvision[cuda]" --extra-index-url https://download.pytorch.org/whl/cu121
   uv sync
   ```

   **For macOS** (uses Metal Performance Shaders):
   ```bash
   uv sync  # MPS support is included automatically
   ```

5. **Run the application**:
   ```bash
   uv run panel serve src/main.py --show
   ```

The application will open automatically in your browser at `http://localhost:5006/main`

### ⚠️ Troubleshooting

If you encounter dependency conflicts:
1. **Clean installation**: `rm -rf .venv && uv sync`
2. **Use CPU mode**: The app automatically fallback to CPU if GPU is not available
3. **Check Python version**: Requires Python ≥3.11

### Alternative Installation Methods

#### Development Mode
```bash
# Install in editable mode
uv pip install -e .

# Or with extras
uv pip install -e ".[dev,gpu,viz]"

# Then run
uv run pymicetracking
```

#### Build and Install
```bash
# Build the package
uv build

# Install the wheel
uv pip install dist/pymicetracking_panel-0.1.0-py3-none-any.whl

# Run via command
pymicetracking
```

#### Traditional pip
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -e .
panel serve src/main.py --show
```

## Installation Extras

Optional dependency groups for modular installation:

```bash
# GPU acceleration (automatically detects CUDA/MPS)
uv sync --extra gpu

# Computer vision models (YOLO)  
uv sync --extra yolo

# Analysis and plotting tools
uv sync --extra viz

# Development tools (testing, linting, formatting)
uv sync --extra dev

# Install all extras
uv sync --all-extras
```

## 🛠️ Development Setup

For contributing to the project, you'll want to set up the development environment with code formatting and linting tools:

### Quick Setup
```bash
# Clone the repository
git clone <repo-url>
cd proj-pymicetracking-panel

# Run the setup script (installs dev dependencies and pre-commit hooks)
./setup-dev.sh
```

### Manual Setup
```bash
# Install pre-commit hooks (runs black, isort, flake8 on each commit)
pre-commit install
```

### Code Quality Tools

The project uses the following tools to maintain code quality:

- **Black**: Code formatter (88 character line length)
- **isort**: Import sorter (compatible with Black)
- **flake8**: Linter for style and error checking
- **pre-commit**: Runs all tools automatically on commit

### Running Tools Manually

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8 src/ tests/

# Run all pre-commit hooks
pre-commit run --all-files
```





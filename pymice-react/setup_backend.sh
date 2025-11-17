#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Configura cache compartilhado do uv
export UV_CACHE_DIR=/mnt/hd3/uv-common/uv-web-yolo

# --- Helper functions ---
print_info() {
    echo "INFO: $1"
}

print_success() {
    echo "✅ SUCCESS: $1"
}

print_error() {
    echo "❌ ERROR: $1" >&2
    exit 1
}

# --- Main script ---

# 1. Check if uv is installed
print_info "Checking if uv is installed..."
if ! command -v uv &> /dev/null; then
    print_error "uv could not be found. Please install uv first. See https://github.com/astral-sh/uv for installation instructions."
fi
print_success "uv is installed."

# 2. Define project structure
BACKEND_DIR="backend"
VENV_DIR="$BACKEND_DIR/venv"
REQUIREMENTS_FILE="$BACKEND_DIR/requirements.txt"
SYMLINK_NAME="uv-env"
PYTHON_VERSION="python3.11"

# 3. Check for required files and directories
print_info "Checking for required files..."
[ ! -d "$BACKEND_DIR" ] && print_error "Backend directory '$BACKEND_DIR' not found."
[ ! -f "$REQUIREMENTS_FILE" ] && print_error "Requirements file '$REQUIREMENTS_FILE' not found."
print_success "Required files found."

# 4. Create the virtual environment
if [ -d "$VENV_DIR" ]; then
    print_info "Virtual environment already exists at '$VENV_DIR'. Skipping creation."
else
    print_info "Creating virtual environment using $PYTHON_VERSION..."
    uv venv -p "$PYTHON_VERSION" "$VENV_DIR"
    print_success "Virtual environment created at '$VENV_DIR'."
fi

# 5. Install dependencies
print_info "Installing dependencies from '$REQUIREMENTS_FILE'..."
uv pip install -r "$REQUIREMENTS_FILE" --python "$VENV_DIR/bin/python"
print_success "Dependencies installed."

# 6. Create symbolic link
if [ -L "$SYMLINK_NAME" ]; then
    print_info "Symbolic link '$SYMLINK_NAME' already exists. Skipping creation."
else
    print_info "Creating symbolic link '$SYMLINK_NAME' -> '$BACKEND_DIR/venv'..."
    ln -s "$BACKEND_DIR/venv" "$SYMLINK_NAME"
    print_success "Symbolic link created."
fi

echo ""
print_success "Backend setup complete!"
print_info "To activate the environment, run: source $SYMLINK_NAME/bin/activate"

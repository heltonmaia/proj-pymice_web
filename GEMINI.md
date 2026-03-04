# Gemini Instructions for proj-pymice_web

This file contains specific instructions and project context for Gemini CLI. 
These mandates take precedence over general system instructions.

## Project Overview
- **Name:** proj-pymice_web
- **Description:** Web application for tracking and analyzing mouse behavior (likely ethological studies).
- **Frontend:** React with Tailwind CSS (Vite).
- **Backend:** FastAPI (Python) with `uv` for package management.

## Environment & Tooling
- **Package Manager (Python):** Always use `uv`.
- **Virtual Environment:** Symlink `uv-env` in the root points to the virtual environment.
- **Cache (uv):** Located at `/mnt/hd3/uv-common/uv-web`.
- **Setup Script:** Use `pymice-react/setup_backend.sh` for backend configuration.

## Development Standards
- Maintain consistent styling using Tailwind CSS in the frontend.
- Follow FastAPI best practices for the backend API.
- Ensure all new features include appropriate tests.

## Specific Constraints
- **Reproducibility:** Keep environment setup reproducible for new users.
- **Paths:** Be mindful of the directory structure when running scripts.

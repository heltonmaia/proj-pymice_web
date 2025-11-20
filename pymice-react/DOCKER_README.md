# 🐳 PyMice Tracking Panel - Docker Deployment Guide

Deploy PyMice Tracking Panel using Docker for easy installation on Windows, Linux, and macOS.

## 📋 Prerequisites

### Required
- **Docker** (20.10 or higher)
- **Docker Compose** (1.29 or higher)

### For GPU Support (Optional)
- NVIDIA GPU with CUDA support
- NVIDIA Docker runtime (`nvidia-docker2`)

## 🚀 Quick Start

### Linux / macOS

```bash
# 1. Clone the repository (if not already)
git clone <repository-url>
cd pymice-react

# 2. Run the interactive menu
./docker.sh

# Or use direct commands:
./docker.sh start       # Start services
./docker.sh status      # Check status
./docker.sh free-ports  # Free occupied ports

# 3. Access the application
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Windows

Use Docker Desktop and WSL2:
```bash
# Run inside WSL2
./docker.sh
```

## 🎮 GPU vs CPU Mode

### CPU Mode (Default)
- ✅ Works on any system
- ✅ No special requirements
- ⏱️ Slower tracking (~10-30 FPS)
- 💾 Lower memory usage

### GPU Mode (NVIDIA GPUs)
- 🎮 Requires NVIDIA GPU
- ⚡ Much faster tracking (~50-100+ FPS)
- 💾 More memory efficient (with FP16)
- 🔧 Requires nvidia-docker2 installation

## 📦 Installation Details

### Install Docker

#### Windows
1. Download [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
2. Install and restart
3. Verify: `docker --version`

#### Linux (Ubuntu/Debian)
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
```

#### macOS
1. Download [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
2. Install and start
3. Verify: `docker --version`

### Install NVIDIA Docker (For GPU Support)

#### Linux Only
```bash
# 1. Install NVIDIA drivers (if not already)
ubuntu-drivers devices
sudo ubuntu-drivers autoinstall

# 2. Install nvidia-docker2
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# 3. Test GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

#### Windows
GPU support in Docker Desktop for Windows:
1. Install [NVIDIA CUDA drivers](https://www.nvidia.com/Download/index.aspx)
2. Enable WSL2 GPU support
3. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html#docker)

## 🛠️ Docker Management

### Interactive Menu (Recommended)
```bash
./docker.sh
```

The interactive menu provides:
- 🚀 Start services (with automatic port checking)
- 🛑 Stop services
- 🔄 Restart services
- 📊 Show status
- 📋 View logs
- 🔓 Free occupied ports
- 🚪 Exit

### Available Commands
```bash
./docker.sh start       # Start services
./docker.sh stop        # Stop services
./docker.sh restart     # Restart services
./docker.sh status      # Show status
./docker.sh logs        # View logs
./docker.sh free-ports  # Free ports
```

## 📂 Data Persistence

### Storage Location
All data is stored in `./backend/temp` (local project directory).

**Note**: Docker images are stored in `/var/lib/docker` by default. If you need to move Docker images to a different location (like `/mnt/hd3/docker`) due to disk space, configure Docker daemon's data-root in `/etc/docker/daemon.json`.

### Volumes Mounted
- `./backend/temp/videos` → Uploaded videos
- `./backend/temp/models` → YOLO models
- `./backend/temp/tracking` → Tracking results
- `./backend/temp/roi_templates` → ROI templates

The directories are automatically created by `docker.sh` when you start the application.

### Backup Data
```bash
# Backup all data
tar -czf pymice-backup-$(date +%Y%m%d).tar.gz backend/temp/

# Restore
tar -xzf pymice-backup-YYYYMMDD.tar.gz
```

## 🔧 Configuration

### Change Ports

Edit `docker-compose.yml`:
```yaml
services:
  frontend:
    ports:
      - "5173:80"  # Frontend (default Vite port)
  backend:
    ports:
      - "8000:8000"  # Backend API
```

To use different ports, change the first number (host port):
```yaml
  frontend:
    ports:
      - "8080:80"  # Access on http://localhost:8080
  backend:
    ports:
      - "9000:8000"  # Access on http://localhost:9000
```

### Environment Variables

Backend (`docker-compose.yml`):
```yaml
environment:
  - PYTHONUNBUFFERED=1
  - CUDA_VISIBLE_DEVICES=""  # For CPU mode
  # Add custom variables here
```

## 📊 Resource Usage

### Minimum Requirements
- **CPU Mode**: 4 GB RAM, 2 CPU cores, 10 GB disk
- **GPU Mode**: 8 GB RAM, 4 GB VRAM, 2 CPU cores, 10 GB disk

### Recommended
- **CPU Mode**: 8 GB RAM, 4 CPU cores, 20 GB disk
- **GPU Mode**: 16 GB RAM, 8 GB VRAM, 4 CPU cores, 20 GB disk

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Check what's using port 5173 (frontend) or 8000 (backend)
sudo lsof -i :5173
sudo lsof -i :8000
# Or use the docker.sh menu option "Free ports"
./docker.sh
```

### Cannot Connect to Docker Daemon
```bash
# Linux: Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Windows: Start Docker Desktop
```

### GPU Not Detected
```bash
# Check NVIDIA drivers
nvidia-smi

# Test Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# Check docker runtime
docker info | grep -i runtime
```

### Container Keeps Restarting
```bash
# View logs
docker-compose logs backend

# Check health
docker ps -a
```

## 🔄 Updates

### Pull Latest Changes
```bash
git pull origin main
./docker.sh restart
```

### Update Docker Images
```bash
docker-compose pull
docker-compose up -d
```

## 🌐 Production Deployment

### Use Production Compose File
Create `docker-compose.prod.yml`:
```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.gpu
    restart: always
    environment:
      - PYTHONUNBUFFERED=1
      - DEBUG=false
    # ... other production settings

  frontend:
    build:
      context: ./frontend
    restart: always
    # ... other production settings
```

### Behind Reverse Proxy (nginx, Traefik, etc.)
```nginx
# Example nginx config
server {
    listen 80;
    server_name pymice.yourdomain.com;

    location / {
        proxy_pass http://localhost:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-docker)
- [PyMice Documentation](./README.md)

## ⚡ Performance Tips

1. **Use GPU mode** for 5-10x faster tracking
2. **Adjust `inference_size`** in UI (lower = faster, less memory)
3. **Close other GPU applications** when tracking
4. **Use SSD storage** for faster video loading
5. **Allocate enough Docker resources** (Settings → Resources)

## 🆘 Support

For issues:
1. Check logs: `docker-compose logs -f`
2. Verify installation: `docker ps`
3. Open an issue with logs attached

---

**Made with ❤️ for mice tracking research**

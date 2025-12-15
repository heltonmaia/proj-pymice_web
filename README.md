# PyMice Web

Modern web application for mouse tracking and behavioral analysis using React + TypeScript and FastAPI.

## Quick Start

### Prerequisites
- Python 3.11
- Node.js >= 18.0
- ffmpeg (for video timestamp extraction)
- CUDA Toolkit 12.4 (optional, for GPU acceleration)

### Recommended Method: Unified Script

The project includes a unified `run.sh` script that automatically manages the entire environment:

```bash
# Make script executable (first time)
chmod +x run.sh

# Start frontend + backend
./run.sh start

# Check services status
./run.sh status

# Stop services
./run.sh stop

# Restart
./run.sh restart

# Interactive menu
./run.sh
```

**UV Virtual Environment:**
- Backend uses a UV environment located in `uv-env/`
- `run.sh` automatically activates the correct environment
- Includes PyTorch 2.6.0 with CUDA 12.4 support

**Check GPU:**
```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

### Manual Installation (Alternative)

**1. Backend:**
```bash
cd backend

# Activate UV environment
source ../uv-env/bin/activate

# Install dependencies (if needed)
pip install -r requirements.txt

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**2. Frontend:**
```bash
cd frontend

# Install dependencies
npm install

# Run in development
npm run dev
```

### Access
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Logs**: `tail -f logs/*.log`

## 📁 Project Structure

```
pymice-react/
├── backend/                 # FastAPI API
│   ├── app/
│   │   ├── routers/        # REST endpoints
│   │   ├── models/         # Pydantic schemas
│   │   ├── processing/     # Processing logic
│   │   └── main.py         # Entry point
│   └── temp/               # Temporary files
│       ├── videos/         # Uploaded videos
│       ├── models/         # YOLO models (.pt)
│       ├── tracking/       # Tracking results
│       └── roi_templates/  # Saved ROI templates
│
└── frontend/               # React application
    ├── src/
    │   ├── components/     # Reusable components
    │   ├── pages/          # Main pages
    │   ├── services/       # API client
    │   ├── types/          # TypeScript types
    │   └── utils/          # Utilities
    └── public/             # Static assets
```

## Features

### 1. Camera Tab
- Live streaming from USB cameras
- Video recording with resolution control
- Download recordings

### 2. Tracking Tab
- **Video upload** and YOLO model selection
- **Interactive ROI drawing**: Rectangle, Circle, Polygon
- **ROI templates**: Save and reuse experiment configurations
- **Real-time tracking** with live visualization
- **Dual detection**: YOLO + Template Matching (fallback)
- **ROI highlighting**: ROIs change color when the animal enters them
- **Results export** in JSON with precise timestamps

### 3. Ethological Analysis Tab
- Movement heatmap analysis
- Speed and distance metrics
- Open Field analysis
- Statistical visualizations

### 4. Extra Tools Tab
- GPU diagnostics (CUDA/MPS/CPU)
- YOLO performance testing
- During tracking, the log automatically shows which device is being used (GPU/CPU)

## 🔧 Technologies

### Frontend
- React 18 + TypeScript
- Vite (build tool)
- TailwindCSS (styling)
- Axios (HTTP client)
- Lucide React (icons)

### Backend
- Python 3.11
- FastAPI (web framework)
- Pydantic (validation)
- PyTorch 2.6.0 (deep learning, CUDA 12.4)
- Ultralytics 8.3.102 (YOLO detection)
- OpenCV (video processing)
- ffmpeg/ffprobe (metadata extraction)

## Main API Endpoints

### Tracking
- `GET /api/tracking/models` - List YOLO models
- `POST /api/tracking/start` - Start tracking
- `GET /api/tracking/progress/{task_id}` - Progress
- `GET /api/tracking/frame/{task_id}` - Current frame (live preview)
- `GET /api/tracking/results/{task_id}` - Download results

### ROI Templates
- `GET /api/tracking/roi-templates/list` - List templates
- `POST /api/tracking/roi-templates/save` - Save template
- `GET /api/tracking/roi-templates/load/{filename}` - Load template
- `DELETE /api/tracking/roi-templates/delete/{filename}` - Delete template

### Camera & Video
- `GET /api/camera/devices` - List cameras
- `POST /api/camera/stream/start` - Start stream
- `POST /api/video/upload` - Upload video

Complete documentation: http://localhost:8000/docs

## How to Use

### Tracking with ROI Templates

1. **Load video** in Tracking tab
2. **Draw ROIs** (Rectangle, Circle or Polygon)
3. **Save as template** with experiment name (e.g., "Open Field Test")
4. **Next times**: just select the template and click "Load"
5. **Start tracking** - visualize in real-time
6. **Download results** in JSON with:
   - Precise timestamps (via ffmpeg)
   - Centroid coordinates
   - Active ROI per frame
   - Detection method (YOLO/template)
   - Complete statistics

### Results JSON Structure

```json
{
  "video_name": "video.mp4",
  "timestamp": "2025-01-15T...",
  "video_info": {
    "total_frames": 1000,
    "fps": 30.0,
    "duration_sec": 33.33,
    "codec": "h264"
  },
  "statistics": {
    "yolo_detections": 800,
    "template_detections": 190,
    "detection_rate": 99.0
  },
  "rois": [...],
  "tracking_data": [
    {
      "frame_number": 0,
      "timestamp_sec": 0.0,
      "centroid_x": 320.5,
      "centroid_y": 240.2,
      "roi": "roi_0",
      "roi_index": 0,
      "detection_method": "yolo"
    }
  ]
}
```

## 📄 License

MIT License

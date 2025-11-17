# PyMiceTracking Web Application

Aplicação web moderna para rastreamento e análise comportamental de camundongos usando React + TypeScript e FastAPI.

## 🚀 Início Rápido

### Pré-requisitos
- Python 3.11
- Node.js >= 18.0
- ffmpeg (para extração de timestamps de vídeo)
- CUDA Toolkit 12.4 (opcional, para aceleração GPU)

### Método Recomendado: Script Unificado

O projeto inclui um script unificado `run.sh` que gerencia todo o ambiente automaticamente:

```bash
# Tornar o script executável (primeira vez)
chmod +x run.sh

# Iniciar frontend + backend
./run.sh start

# Ver status dos serviços
./run.sh status

# Parar serviços
./run.sh stop

# Reiniciar
./run.sh restart

# Menu interativo
./run.sh
```

**Ambiente Virtual UV:**
- O backend usa um ambiente UV localizado em `uv-env/`
- O `run.sh` ativa automaticamente o ambiente correto
- Inclui PyTorch 2.6.0 com suporte CUDA 12.4

**Verificar GPU:**
```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

### Instalação Manual (Alternativa)

**1. Backend:**
```bash
cd backend

# Ativar ambiente UV
source ../uv-env/bin/activate

# Instalar dependências (se necessário)
pip install -r requirements.txt

# Executar servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**2. Frontend:**
```bash
cd frontend

# Instalar dependências
npm install

# Executar em desenvolvimento
npm run dev
```

### Acesso
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Logs**: `tail -f logs/*.log`

## 📁 Estrutura do Projeto

```
pymice-react/
├── backend/                 # API FastAPI
│   ├── app/
│   │   ├── routers/        # Endpoints REST
│   │   ├── models/         # Schemas Pydantic
│   │   ├── processing/     # Lógica de processamento
│   │   └── main.py         # Entry point
│   └── temp/               # Arquivos temporários
│       ├── videos/         # Vídeos uploaded
│       ├── models/         # Modelos YOLO (.pt)
│       ├── tracking/       # Resultados de tracking
│       └── roi_templates/  # Templates de ROI salvos
│
└── frontend/               # Aplicação React
    ├── src/
    │   ├── components/     # Componentes reutilizáveis
    │   ├── pages/          # Páginas principais
    │   ├── services/       # Cliente API
    │   ├── types/          # Tipos TypeScript
    │   └── utils/          # Utilitários
    └── public/             # Assets estáticos
```

## ✨ Funcionalidades

### 1. Camera Tab
- Streaming ao vivo de câmeras USB
- Gravação de vídeo com controle de resolução
- Download de gravações

### 2. Tracking Tab
- **Upload de vídeo** e seleção de modelo YOLO
- **Desenho interativo de ROIs**: Rectangle, Circle, Polygon
- **Templates de ROI**: Salve e reutilize configurações de experimentos
- **Tracking em tempo real** com visualização ao vivo
- **Detecção dual**: YOLO + Template Matching (fallback)
- **ROI highlighting**: ROIs mudam de cor quando o animal entra nelas
- **Export de resultados** em JSON com timestamps precisos

### 3. Ethological Analysis Tab
- Análise de heatmap de movimento
- Métricas de velocidade e distância
- Análise de Open Field
- Visualizações estatísticas

### 4. Extra Tools Tab
- Diagnóstico de GPU (CUDA/MPS/CPU)
- Teste de performance YOLO
- Durante o tracking, o log mostra automaticamente qual device está sendo usado (GPU/CPU)

## 🔧 Tecnologias

### Frontend
- React 18 + TypeScript
- Vite (build tool)
- TailwindCSS (styling)
- Axios (HTTP client)
- Lucide React (ícones)

### Backend
- Python 3.11
- FastAPI (framework web)
- Pydantic (validação)
- PyTorch 2.6.0 (deep learning, CUDA 12.4)
- Ultralytics 8.3.102 (YOLO detecção)
- OpenCV (processamento de vídeo)
- ffmpeg/ffprobe (extração de metadados)

## 📡 API Endpoints Principais

### Tracking
- `GET /api/tracking/models` - Listar modelos YOLO
- `POST /api/tracking/start` - Iniciar rastreamento
- `GET /api/tracking/progress/{task_id}` - Progresso
- `GET /api/tracking/frame/{task_id}` - Frame atual (live preview)
- `GET /api/tracking/results/{task_id}` - Download resultados

### ROI Templates
- `GET /api/tracking/roi-templates/list` - Listar templates
- `POST /api/tracking/roi-templates/save` - Salvar template
- `GET /api/tracking/roi-templates/load/{filename}` - Carregar template
- `DELETE /api/tracking/roi-templates/delete/{filename}` - Deletar template

### Camera & Video
- `GET /api/camera/devices` - Listar câmeras
- `POST /api/camera/stream/start` - Iniciar stream
- `POST /api/video/upload` - Upload de vídeo

Documentação completa: http://localhost:8000/docs

## 🎯 Como Usar

### Rastreamento com Templates de ROI

1. **Carregar vídeo** na aba Tracking
2. **Desenhar ROIs** (Rectangle, Circle ou Polygon)
3. **Salvar como template** com nome do experimento (ex: "Open Field Test")
4. **Próximas vezes**: apenas selecione o template e clique em "Load"
5. **Iniciar tracking** - visualize em tempo real
6. **Download dos resultados** em JSON com:
   - Timestamps precisos (via ffmpeg)
   - Coordenadas do centroid
   - ROI ativa por frame
   - Método de detecção (YOLO/template)
   - Estatísticas completas

### Estrutura do JSON de Resultados

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

## 🐛 Resolução de Problemas

### Modelos YOLO não aparecem
1. Verifique se há arquivos `.pt` em `backend/temp/models/`
2. Recarregue a página (Ctrl+Shift+R)
3. Verifique o console do backend para erros

### Porta já em uso
```bash
# Linux/Mac
kill $(lsof -t -i:8000)  # Backend
kill $(lsof -t -i:5173)  # Frontend

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Erro ao processar vídeo
- Verifique se ffmpeg está instalado: `ffmpeg -version`
- Confirme que o modelo YOLO é compatível (ultralytics >= 8.3.0)
- Veja logs do backend para detalhes

### Frontend não conecta ao backend
- Confirme que o backend está rodando na porta 8000
- Verifique o proxy no `vite.config.ts`
- Abra as DevTools e veja a aba Network

## 📝 Notas Importantes

- **Modelos YOLO**: Coloque arquivos `.pt` em `backend/temp/models/`
- **GPU**: Auto-detecta CUDA/MPS, fallback para CPU
- **Detecção Dual**: YOLO primeiro, template matching como fallback
- **Timestamps**: Extraídos via ffmpeg/ffprobe para máxima precisão
- **Live Preview**: Atualiza a cada 500ms durante tracking

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

MIT License

---

**Desenvolvido com ❤️ usando React, TypeScript e FastAPI**

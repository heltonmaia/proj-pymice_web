# PyMiceTracking Web Application

Uma aplicação web moderna para rastreamento e análise comportamental de camundongos usando React + TypeScript e FastAPI.

## 📋 Visão Geral

Esta é uma recriação completa da aplicação PyMiceTracking Panel original, agora com uma arquitetura moderna cliente-servidor:

- **Frontend**: React + TypeScript + Vite + TailwindCSS
- **Backend**: FastAPI + Python + OpenCV + YOLO

## 🏗️ Estrutura do Projeto

```
app-web/
├── frontend/               # Aplicação React
│   ├── src/
│   │   ├── components/    # Componentes reutilizáveis
│   │   ├── pages/         # Páginas/Tabs principais
│   │   ├── services/      # Cliente API
│   │   ├── types/         # Tipos TypeScript
│   │   ├── utils/         # Utilitários
│   │   └── App.tsx        # Componente principal
│   ├── package.json
│   └── vite.config.ts
│
└── backend/               # API FastAPI
    ├── app/
    │   ├── routers/       # Endpoints da API
    │   ├── models/        # Schemas Pydantic
    │   ├── services/      # Lógica de negócio
    │   └── main.py        # Entry point
    ├── pyproject.toml
    └── requirements.txt
```

## 🚀 Funcionalidades

### 1. Camera Tab
- **Streaming ao vivo** de câmeras USB
- **Gravação de vídeo** com controle de resolução
- Suporte para múltiplas câmeras
- Download de gravações

### 2. Tracking Tab
- **Rastreamento YOLO** com modelos customizados
- **Desenho interativo de ROIs** (Rectangle, Circle, Polygon)
- Configuração de thresholds (confidence, IOU)
- Visualização em tempo real do progresso
- Export de dados de rastreamento (JSON)

### 3. Ethological Analysis Tab
- **Análise de heatmap** de movimento
- **Métricas de movimento**: velocidade, distância, centro de massa
- **Análise de Open Field**: tempo em centro vs periferia
- Visualizações estatísticas completas
- Export de gráficos e análises

### 4. Extra Tools Tab
- **Diagnóstico de GPU** (CUDA/MPS)
- **Teste de performance** YOLO (GPU vs CPU)
- Informações do sistema

### 5. Synthetic Data & IRL Analysis
- Placeholders para futuras implementações

## 📦 Instalação

### Pré-requisitos

- **Node.js** >= 18.0.0
- **Python** >= 3.11
- **npm** ou **yarn** (para frontend)
- **pip** ou **uv** (para backend)

### Frontend

```bash
cd app-web/frontend

# Instalar dependências
npm install

# Executar em modo desenvolvimento
npm run dev

# Build para produção
npm run build
```

O frontend estará disponível em `http://localhost:5173`

### Backend

```bash
cd app-web/backend

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows

# Instalar dependências
pip install -r requirements.txt

# OU usando uv (recomendado)
uv sync

# Executar servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

O backend estará disponível em `http://localhost:8000`
Documentação da API: `http://localhost:8000/docs`

### Instalação Completa com GPU (Opcional)

Para habilitar aceleração GPU (NVIDIA CUDA ou Apple Silicon MPS):

```bash
# PyTorch com CUDA (NVIDIA)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# OU PyTorch com suporte MPS (Apple Silicon)
pip install torch torchvision

# YOLO
pip install ultralytics>=8.0.0
```

## 🔧 Configuração

### Backend (.env)

Copie o arquivo `.env.example` para `.env` e configure:

```env
HOST=0.0.0.0
PORT=8000
DEBUG=True
CORS_ORIGINS=http://localhost:5173,http://localhost:5173
```

### Frontend

As configurações estão no `vite.config.ts`. O proxy está configurado para redirecionar `/api` para `http://localhost:8000`.

## 📖 Uso

### 1. Gravação de Vídeo

1. Acesse a aba **Camera**
2. Selecione o dispositivo de câmera
3. Escolha a resolução desejada
4. Clique em **Start Stream** para visualizar
5. Clique em **Start Recording** para gravar
6. **Stop Recording** e faça o download

### 2. Rastreamento de Movimento

1. Acesse a aba **Tracking**
2. Faça upload de um vídeo ou use um gravado
3. Selecione o modelo YOLO (ou faça upload de um customizado)
4. Desenhe os ROIs clicando e arrastando no canvas
5. Ajuste os thresholds de detecção
6. Clique em **Start Tracking**
7. Aguarde o processamento
8. Download dos resultados em JSON

### 3. Análise Etológica

1. Acesse a aba **Ethological Analysis**
2. Faça upload do vídeo e do JSON de rastreamento
3. Selecione o tipo de análise:
   - **Complete Analysis**: Painel completo com todas métricas
   - **Heatmap Only**: Apenas mapa de calor
   - **Movement Analysis**: Gráficos de velocidade e trajetória
4. Configure parâmetros do heatmap (resolução, colormap, transparência)
5. Clique em **Generate Analysis**
6. Visualize e exporte os resultados

## 🎨 Tecnologias Utilizadas

### Frontend
- **React 18** - UI Library
- **TypeScript** - Type Safety
- **Vite** - Build Tool
- **TailwindCSS** - Styling
- **React Konva** - Canvas Drawing
- **Axios** - HTTP Client
- **Zustand** - State Management
- **TanStack Query** - Data Fetching
- **Recharts** - Charts & Visualizations
- **Lucide React** - Icons

### Backend
- **FastAPI** - Web Framework
- **Pydantic** - Data Validation
- **OpenCV** - Computer Vision
- **NumPy/Pandas** - Data Processing
- **Matplotlib/Seaborn** - Visualizations
- **PyTorch** - Deep Learning (opcional)
- **Ultralytics YOLO** - Object Detection (opcional)

## 🔌 API Endpoints

### Camera
- `GET /api/camera/devices` - Listar câmeras disponíveis
- `POST /api/camera/stream/start` - Iniciar stream
- `POST /api/camera/stream/stop` - Parar stream
- `GET /api/camera/frame` - Obter frame atual
- `POST /api/camera/record/start` - Iniciar gravação
- `POST /api/camera/record/stop` - Parar gravação

### Video
- `POST /api/video/upload` - Upload de vídeo
- `GET /api/video/info/{filename}` - Informações do vídeo
- `GET /api/video/download/{filename}` - Download de vídeo
- `GET /api/video/list` - Listar vídeos

### Tracking
- `GET /api/tracking/models` - Listar modelos YOLO
- `POST /api/tracking/models/upload` - Upload de modelo
- `POST /api/tracking/start` - Iniciar rastreamento
- `GET /api/tracking/progress/{task_id}` - Progresso do rastreamento
- `POST /api/tracking/stop/{task_id}` - Parar rastreamento
- `GET /api/tracking/results/{task_id}` - Download de resultados

### ROI
- `GET /api/roi/presets` - Listar presets
- `GET /api/roi/presets/{name}` - Carregar preset
- `POST /api/roi/presets` - Salvar preset
- `DELETE /api/roi/presets/{name}` - Deletar preset

### Analysis
- `POST /api/analysis/heatmap` - Gerar heatmap
- `POST /api/analysis/movement` - Análise de movimento
- `POST /api/analysis/open-field` - Análise Open Field
- `POST /api/analysis/export-video` - Exportar vídeo com overlay

### System
- `GET /api/system/gpu` - Status da GPU
- `POST /api/system/test-yolo` - Teste de performance

## 🤝 Comparação com a Versão Original

| Recurso | Original (Panel) | Web (React) |
|---------|-----------------|-------------|
| Framework UI | Panel/Bokeh | React + TypeScript |
| Arquitetura | Monolítica | Cliente-Servidor |
| API | Interno | REST API (FastAPI) |
| Estado | Callbacks Python | React Hooks + Zustand |
| Canvas | Bokeh Canvas | HTML5 Canvas + Konva |
| Styling | Panel CSS | TailwindCSS |
| Deployment | Single Server | Frontend + Backend separados |
| Performance | Boa | Excelente (otimizado) |

## 📝 Próximos Passos

- [ ] Implementar processamento YOLO real no backend
- [ ] Adicionar suporte para múltiplos animais
- [ ] Implementar análise de Open Field completa
- [ ] Adicionar autenticação de usuários
- [ ] Sistema de cache para resultados
- [ ] WebSocket para progresso em tempo real
- [ ] Exportar vídeo com overlay
- [ ] Testes unitários e E2E
- [ ] Docker deployment
- [ ] CI/CD pipeline

## 📄 Licença

MIT License - Veja o arquivo LICENSE no diretório raiz do projeto.

## 👥 Contribuindo

Contribuições são bem-vindas! Por favor, abra uma issue ou pull request.

## 📧 Suporte

Para questões e suporte, abra uma issue no repositório.

---

**Desenvolvido com ❤️ usando React, TypeScript e FastAPI**

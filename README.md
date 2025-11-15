# PyMiceTracking - Mouse Behavioral Analysis Platform

Sistema completo para rastreamento e análise comportamental de camundongos usando visão computacional e deep learning.

## 📂 Estrutura do Projeto

Este repositório contém **duas aplicações** para análise de comportamento de camundongos:

```
proj-pymicetracking-panel/
├── .venv/                  # Ambiente virtual Python compartilhado
│
├── pymice-panel/           # 🎨 Aplicação Web Original (Panel + Bokeh)
│   ├── src/                # Código fonte
│   ├── tests/              # Testes unitários
│   ├── experiments/        # Configurações de experimentos
│   └── pyproject.toml      # Dependências e configuração
│
└── pymice-react/          # ⚛️ Nova Aplicação Web (React + TypeScript)
    ├── frontend/          # Interface React + TypeScript
    ├── backend/           # API FastAPI + Python
    ├── run.sh            # Script de controle
    └── README.md         # Documentação detalhada
```

---

## 🎨 PyMiceTracking Panel (Original)

Aplicação web usando **Panel + Bokeh** para análise comportamental.

### Características
- Interface web interativa com Panel
- Rastreamento YOLO integrado
- Análise de movimento em tempo real
- Suporte para múltiplos tipos de experimentos
- Visualizações interativas com Bokeh

### Como Usar

```bash
# 1. Ativar ambiente virtual
source .venv/bin/activate

# 2. Instalar dependências (primeira vez)
cd pymice-panel
uv sync

# 3. Executar aplicação
panel serve src/main.py --show

# Acesse: http://localhost:5006
```

### Tecnologias
- **Python** 3.11+
- **Panel** - Framework web
- **Bokeh** - Visualizações interativas
- **YOLOv11** - Detecção de objetos
- **OpenCV** - Processamento de vídeo

📚 **Documentação:** `pymice-panel/readme.md`

---

## ⚛️ PyMiceTracking React (Nova Versão)

Aplicação moderna com **React + TypeScript** no frontend e **FastAPI** no backend.

### Características
- Interface moderna e responsiva
- Arquitetura cliente-servidor
- API REST completa
- Desenho interativo de ROIs
- Análise de heatmaps avançada
- Deploy com Docker

### Como Usar

```bash
# Executar menu interativo
cd pymice-react
./run.sh

# Escolha uma opção:
# 1) 🚀 Iniciar Serviços
# 2) 🛑 Parar Serviços
# 3) 🔄 Reiniciar
# 4) 📊 Ver Status
# 0) Sair

# Acesse: http://localhost:5173
```

### Tecnologias

**Frontend:**
- React 18 + TypeScript
- Vite (build tool)
- TailwindCSS
- React Konva (canvas)
- Axios + TanStack Query

**Backend:**
- FastAPI
- Pydantic
- OpenCV
- YOLOv11 (opcional)
- PyTorch (opcional)

📚 **Documentação:** `pymice-react/README.md`

---

## 🔧 Ambiente Virtual Compartilhado

Ambas as aplicações usam o mesmo ambiente virtual Python localizado na **raiz** do projeto (`.venv/`).

### Setup Inicial

```bash
# Criar ambiente virtual (primeira vez)
python3 -m venv .venv

# Ativar
source .venv/bin/activate

# Instalar dependências do Panel
cd pymice-panel
uv sync
cd ..

# Instalar dependências do React backend
cd pymice-react/backend
pip install -r requirements.txt
cd ../..
```

### Ativar Ambiente

```bash
# Em qualquer lugar do projeto
source .venv/bin/activate
```

---

## 📊 Comparação das Aplicações

| Característica | Panel (Original) | React (Nova) |
|---------------|------------------|--------------|
| **Framework UI** | Panel + Bokeh | React + TypeScript |
| **Arquitetura** | Monolítica | Cliente-Servidor |
| **API** | Interno | REST (FastAPI) |
| **Deploy** | Single Server | Frontend + Backend |
| **Performance** | Boa | Excelente |
| **Manutenção** | Média | Fácil |
| **Extensibilidade** | Limitada | Alta |
| **Mobile** | Básico | Responsivo |

---

## 🚀 Quick Start

### Opção 1: Aplicação Panel (Original)
```bash
source .venv/bin/activate
cd pymice-panel
panel serve src/main.py --show
```

### Opção 2: Aplicação React (Nova)
```bash
cd pymice-react
./run.sh
# Escolha opção 1 para iniciar
```

---

## 📖 Funcionalidades Principais

### Ambas as Aplicações Incluem:

1. **Camera Tab**
   - Streaming de vídeo ao vivo
   - Gravação de experimentos
   - Suporte para múltiplas câmeras

2. **Tracking Tab**
   - Rastreamento com YOLO
   - Desenho de ROIs (Rectangle, Circle, Polygon)
   - Ajuste de parâmetros de detecção
   - Export de dados

3. **Ethological Analysis**
   - Análise de movimento
   - Heatmaps de densidade
   - Métricas comportamentais
   - Open Field test

4. **Extra Tools**
   - Diagnóstico de GPU
   - Teste de performance YOLO
   - Informações do sistema

---

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

---

## 📝 Licença

MIT License - Veja o arquivo LICENSE para detalhes.

---

## 👥 Autores

- **Aplicação Panel Original** - Sistema de análise comportamental
- **Aplicação React** - Recriação moderna web-based

---

## 🆘 Suporte

- **Issues:** Abra uma issue no GitHub
- **Documentação Panel:** `pymice-panel/readme.md`
- **Documentação React:** `pymice-react/README.md`

---

**Escolha a aplicação que melhor atende suas necessidades!** 🐭🔬

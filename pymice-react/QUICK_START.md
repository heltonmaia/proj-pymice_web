# Quick Start Guide - PyMiceTracking Web

Guia rápido para iniciar a aplicação em modo desenvolvimento.

## 🚀 Início Rápido (5 minutos)

### Passo 1: Backend

```bash
# Navegar para o backend
cd app-web/backend

# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Executar servidor
uvicorn app.main:app --reload
```

✅ Backend rodando em `http://localhost:8000`
📚 API Docs em `http://localhost:8000/docs`

### Passo 2: Frontend

**Em outro terminal:**

```bash
# Navegar para o frontend
cd app-web/frontend

# Instalar dependências
npm install

# Executar em desenvolvimento
npm run dev
```

✅ Frontend rodando em `http://localhost:5173`

### Passo 3: Acessar a Aplicação

Abra seu navegador em `http://localhost:5173` e comece a usar!

## 🐳 Usando Docker (Alternativa)

Se preferir usar Docker:

```bash
cd app-web

# Iniciar todos os serviços
docker-compose up

# OU em background
docker-compose up -d

# Parar serviços
docker-compose down
```

## 📋 Checklist de Funcionalidades

Teste as seguintes funcionalidades na ordem:

### 1. Camera Tab
- [ ] Listar câmeras disponíveis
- [ ] Iniciar stream de vídeo
- [ ] Gravar vídeo
- [ ] Baixar gravação

### 2. Tracking Tab
- [ ] Fazer upload de vídeo
- [ ] Desenhar ROIs (Rectangle, Circle)
- [ ] Ajustar thresholds
- [ ] Iniciar rastreamento (simulado)
- [ ] Baixar resultados JSON

### 3. Ethological Analysis Tab
- [ ] Upload de vídeo + JSON
- [ ] Configurar heatmap
- [ ] Gerar análise
- [ ] Visualizar estatísticas

### 4. Extra Tools Tab
- [ ] Verificar status GPU
- [ ] Executar teste de performance

## 🔧 Resolução de Problemas

### Backend não inicia
```bash
# Verificar se a porta 8000 está livre
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows

# Instalar dependências faltantes
pip install -r requirements.txt
```

### Frontend não inicia
```bash
# Limpar cache e reinstalar
rm -rf node_modules package-lock.json
npm install

# Verificar se a porta 3000 está livre
lsof -i :3000  # Linux/Mac
netstat -ano | findstr :3000  # Windows
```

### Erro de CORS
Verifique se o backend está rodando em `http://localhost:8000` e o frontend em `http://localhost:5173` ou `http://localhost:5173`.

### Câmera não detectada
- Permita acesso à câmera no navegador
- Verifique se a câmera está conectada
- Teste em outro navegador

## 📦 Próximos Passos

1. **Adicionar modelo YOLO real**
   - Baixe um modelo YOLOv11: https://docs.ultralytics.com/
   - Coloque em `backend/temp/models/`

2. **Testar com vídeos reais**
   - Use vídeos de experimentos com camundongos
   - Configure ROIs apropriados
   - Execute análises

3. **Customizar**
   - Ajuste cores e temas no TailwindCSS
   - Adicione novos tipos de análise
   - Implemente algoritmos customizados

## 🎯 Comandos Úteis

### Backend
```bash
# Executar com auto-reload
uvicorn app.main:app --reload

# Executar em produção
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Ver documentação da API
# Abra http://localhost:8000/docs
```

### Frontend
```bash
# Desenvolvimento
npm run dev

# Build
npm run build

# Preview do build
npm run preview

# Lint
npm run lint
```

## 📚 Recursos Adicionais

- **Documentação completa**: Veja `README.md`
- **API Docs**: http://localhost:8000/docs
- **Código original**: `../src/pymicetracking_panel/`

---

**Pronto para começar!** 🎉

Se tiver problemas, consulte o README.md ou abra uma issue.

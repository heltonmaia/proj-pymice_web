# Setup do Backend

## Configuração do Ambiente

O ambiente virtual está localizado em `/mnt/hd3/uv-common/pymice-react-venv` e é acessado via link simbólico `backend/venv`.

O cache do UV está compartilhado em `/mnt/hd3/uv-common/uv-web-yolo`.

## Como Executar

### Setup Inicial
```bash
./setup_backend.sh
```

### Ativar Ambiente
```bash
source uv-env/bin/activate
```

### Iniciar Backend
```bash
./run.sh start
```

### Parar Backend
```bash
./run.sh stop
```

## Pacotes Principais
- Python 3.11
- FastAPI
- PyTorch 2.6.0 (CUDA 12.4)
- Ultralytics 8.3.102
- OpenCV

## Verificar CUDA
```bash
backend/venv/bin/python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

import os
import subprocess
import sys
import shutil
import time
from pathlib import Path

# Configurações
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
PROJECT_ROOT = Path(__file__).parent.absolute()
VENV_PATH = PROJECT_ROOT / "uv-env"

# Pastas para limpeza (NÃO incluir 'models' aqui)
CLEANUP_DIRS = [
    PROJECT_ROOT / "backend" / "temp" / "videos",
    PROJECT_ROOT / "backend" / "temp" / "tracking",
    PROJECT_ROOT / "backend" / "temp" / "analysis",
    PROJECT_ROOT / "logs"
]

def clean_temporaries():
    """Limpa arquivos temporários e caches, preservando modelos."""
    print("🧹 Realizando limpeza seletiva...")
    
    # 1. Limpar __pycache__ e arquivos .pyc no backend
    backend_path = PROJECT_ROOT / "backend"
    if backend_path.exists():
        for root, dirs, files in os.walk(backend_path):
            if "__pycache__" in dirs:
                shutil.rmtree(Path(root) / "__pycache__", ignore_errors=True)
            for f in files:
                if f.endswith(".pyc"):
                    try: os.remove(Path(root) / f)
                    except: pass

    # 2. Limpar pastas de dados temporários (EXCETO models)
    for temp_dir in CLEANUP_DIRS:
        if temp_dir.exists():
            print(f"   Limpando: {temp_dir.name}...")
            for item in temp_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                except Exception as e:
                    print(f"      Erro ao remover {item.name}: {e}")
        else:
            temp_dir.mkdir(parents=True, exist_ok=True)

    print("✅ Limpeza concluída (Pesos em 'temp/models' preservados).")

def get_python_executable():
    """Localiza o python do ambiente virtual de forma multiplataforma."""
    # Tenta Windows (Scripts) e Linux (bin)
    win_python = VENV_PATH / "Scripts" / "python.exe"
    linux_python = VENV_PATH / "bin" / "python"
    
    if win_python.exists():
        return str(win_python)
    if linux_python.exists():
        return str(linux_python)
    
    # Se for um link simbólico quebrado, tenta resolver o realpath
    try:
        real_venv = VENV_PATH.resolve()
        win_python_real = real_venv / "Scripts" / "python.exe"
        linux_python_real = real_venv / "bin" / "python"
        if win_python_real.exists(): return str(win_python_real)
        if linux_python_real.exists(): return str(linux_python_real)
    except:
        pass

    print(f"❌ Erro: Ambiente virtual não encontrado em {VENV_PATH}")
    print("Por favor, execute './setup_backend.sh' no Linux para criar o ambiente no HD externo.")
    sys.exit(1)

def run_services():
    python_exe = get_python_executable()
    processes = []
    
    try:
        # 1. Iniciar Backend
        print(f"🚀 Iniciando Backend (Porta {BACKEND_PORT})...")
        backend_dir = PROJECT_ROOT / "backend"
        backend_cmd = [
            python_exe, "-m", "uvicorn", 
            "app.main:app", 
            "--host", "0.0.0.0", 
            "--port", str(BACKEND_PORT),
            "--reload"
        ]
        p_backend = subprocess.Popen(backend_cmd, cwd=backend_dir)
        processes.append(p_backend)

        # 2. Iniciar Frontend
        print(f"🚀 Iniciando Frontend (Porta {FRONTEND_PORT})...")
        frontend_dir = PROJECT_ROOT / "frontend"
        # No Windows, npm precisa de shell=True
        use_shell = (os.name == "nt")
        frontend_cmd = ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", str(FRONTEND_PORT)]
        p_frontend = subprocess.Popen(frontend_cmd, cwd=frontend_dir, shell=use_shell)
        processes.append(p_frontend)

        print("
✨ PyMice Web está pronto!")
        print(f"🔗 URL: http://localhost:{FRONTEND_PORT}")
        print("Pressione Ctrl+C para parar todos os serviços.
")

        # Monitorar processos
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"
⚠️ Um dos serviços (PID {p.pid}) parou inesperadamente.")
                    return

    except KeyboardInterrupt:
        print("
🛑 Encerrando serviços...")
    finally:
        for p in processes:
            p.terminate()
            try: p.wait(timeout=2)
            except: p.kill()
        print("👋 Sistema encerrado.")

if __name__ == "__main__":
    clean_temporaries()
    run_services()

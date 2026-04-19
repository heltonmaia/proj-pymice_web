#!/bin/bash

# PyMice Web - Script Unificado
# Uso: ./run.sh [start|stop|status|restart]

set -e

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configurações
BACKEND_PORT=8765
FRONTEND_PORT=5765
LOG_DIR="logs"
PID_DIR="$LOG_DIR"

# Banner
show_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║           PyMice Web - Control Script                          ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}\n"
}

# Verificar se porta está em uso
check_port() {
    lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1
}

# Verificar status dos serviços
check_status() {
    local backend_running=false
    local frontend_running=false

    if check_port $BACKEND_PORT; then
        backend_running=true
    fi

    if check_port $FRONTEND_PORT; then
        frontend_running=true
    fi

    echo "$backend_running $frontend_running"
}

# Limpar temporários
clean_temporaries() {
    echo -e "${YELLOW}🧹 Realizando limpeza seletiva...${NC}"
    
    # 1. Limpar __pycache__ e arquivos .pyc no backend
    find backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find backend -name "*.pyc" -delete 2>/dev/null || true

    # 2. Limpar pastas de dados temporários (EXCETO models)
    CLEANUP_DIRS=("backend/temp/videos" "backend/temp/tracking" "backend/temp/analysis" "logs")
    for dir in "${CLEANUP_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            echo -e "   Limpando: ${dir}..."
            rm -rf "$dir"/* 2>/dev/null || true
        else
            mkdir -p "$dir"
        fi
    done

    echo -e "${GREEN}✅ Limpeza concluída (Pesos em 'backend/temp/models' preservados).${NC}"
}

# Mostrar status
show_status() {
    show_banner

    echo -e "${BLUE}📊 Status dos Serviços:${NC}\n"

    # Backend
    if check_port $BACKEND_PORT; then
        echo -e "   Backend:  ${GREEN}● RODANDO${NC} (porta $BACKEND_PORT)"
        if [ -f "$PID_DIR/backend.pid" ]; then
            PID=$(cat "$PID_DIR/backend.pid")
            echo -e "             PID: ${YELLOW}$PID${NC}"
        fi
    else
        echo -e "   Backend:  ${RED}○ PARADO${NC}"
    fi

    # Frontend
    if check_port $FRONTEND_PORT; then
        echo -e "   Frontend: ${GREEN}● RODANDO${NC} (porta $FRONTEND_PORT)"
        if [ -f "$PID_DIR/frontend.pid" ]; then
            PID=$(cat "$PID_DIR/frontend.pid")
            echo -e "             PID: ${YELLOW}$PID${NC}"
        fi
    else
        echo -e "   Frontend: ${RED}○ PARADO${NC}"
    fi

    echo ""
    echo -e "${BLUE}📱 URLs:${NC}"
    echo -e "   Frontend:    ${CYAN}http://localhost:$FRONTEND_PORT${NC}"
    echo -e "   Backend API: ${CYAN}http://localhost:$BACKEND_PORT${NC}"
    echo -e "   API Docs:    ${CYAN}http://localhost:$BACKEND_PORT/docs${NC}"

    if [ -f "$LOG_DIR/backend.log" ] || [ -f "$LOG_DIR/frontend.log" ]; then
        echo ""
        echo -e "${BLUE}📝 Logs:${NC}"
        [ -f "$LOG_DIR/backend.log" ] && echo -e "   Backend:  ${YELLOW}tail -f $LOG_DIR/backend.log${NC}"
        [ -f "$LOG_DIR/frontend.log" ] && echo -e "   Frontend: ${YELLOW}tail -f $LOG_DIR/frontend.log${NC}"
    fi

    echo ""
}

# Iniciar serviços
start_services() {
    show_banner

    clean_temporaries

    echo -e "${GREEN}🚀 Iniciando PyMice Web...${NC}\n"

    # Verificar se já está rodando
    read backend_status frontend_status <<< $(check_status)

    if [ "$backend_status" = "true" ] && [ "$frontend_status" = "true" ]; then
        echo -e "${YELLOW}⚠${NC}  Serviços já estão rodando!"
        echo ""
        show_status
        exit 0
    fi

    # Verificar dependências básicas
    echo -e "${BLUE}📋 Verificando dependências...${NC}"

    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}✗ Python 3 não encontrado!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Python: $(python3 --version)"

    if ! command -v node &> /dev/null; then
        echo -e "${RED}✗ Node.js não encontrado!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Node.js: $(node --version)"

    echo ""

    # Criar diretórios
    mkdir -p "$LOG_DIR"

    # Configurar e iniciar Backend
    if [ "$backend_status" = "false" ]; then
        echo -e "${BLUE}🐍 Configurando Backend...${NC}"

        cd backend

        # Verificar ambiente virtual UV
        VENV_PATH="/mnt/hd3/uv-common/pymice-react-venv"

        if [ ! -d "$VENV_PATH" ]; then
            echo ""
            echo -e "${RED}✗ Ambiente virtual UV não encontrado em $VENV_PATH${NC}"
            echo ""
            echo -e "${YELLOW}Solução:${NC}"
            echo "  Crie o ambiente manualmente ou verifique o caminho."
            echo ""
            cd ..
            exit 1
        fi

        # Verificar se o ambiente já está ativo
        if [ -z "$VIRTUAL_ENV" ]; then
            echo ""
            echo -e "${RED}✗ Ambiente virtual não está ativo!${NC}"
            echo ""
            echo -e "${YELLOW}Ative manualmente antes de executar:${NC}"
            echo -e "  ${CYAN}source $VENV_PATH/bin/activate${NC}"
            echo ""
            cd ..
            exit 1
        fi

        echo "   Usando ambiente virtual: $VIRTUAL_ENV"

        # Criar diretórios temp
        mkdir -p temp/{videos,models,tracking,analysis}

        # Iniciar backend em background
        echo "   Iniciando servidor..."
        nohup uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT > "../$LOG_DIR/backend.log" 2>&1 &
        echo $! > "../$PID_DIR/backend.pid"

        cd ..

        echo -e "${GREEN}✓${NC} Backend iniciado"
        sleep 2
    else
        echo -e "${YELLOW}⚠${NC}  Backend já está rodando"
    fi

    # Configurar e iniciar Frontend
    if [ "$frontend_status" = "false" ]; then
        echo -e "${BLUE}⚛️  Configurando Frontend...${NC}"

        cd frontend

        # Instalar dependências
        if [ ! -d "node_modules" ]; then
            echo "   Instalando dependências..."
            npm install --silent
        fi

        # Iniciar frontend em background
        echo "   Iniciando servidor..."
        nohup npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT > "../$LOG_DIR/frontend.log" 2>&1 &
        echo $! > "../$PID_DIR/frontend.pid"

        cd ..

        echo -e "${GREEN}✓${NC} Frontend iniciado"
        sleep 3
    else
        echo -e "${YELLOW}⚠${NC}  Frontend já está rodando"
    fi

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                   ✓ Serviços Iniciados!                       ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}📱 Acesse: ${BLUE}http://localhost:$FRONTEND_PORT${NC}"
    echo ""
    echo -e "${YELLOW}Comandos úteis:${NC}"
    echo -e "   Status:   ${CYAN}./run.sh status${NC}"
    echo -e "   Parar:    ${CYAN}./run.sh stop${NC}"
    echo -e "   Logs:     ${CYAN}tail -f logs/*.log${NC}"
    echo ""

    # Abrir navegador
    if command -v xdg-open &> /dev/null; then
        sleep 1
        xdg-open "http://localhost:$FRONTEND_PORT" 2>/dev/null &
    elif command -v open &> /dev/null; then
        sleep 1
        open "http://localhost:$FRONTEND_PORT" 2>/dev/null &
    fi
}

# Parar serviços
stop_services() {
    show_banner

    echo -e "${YELLOW}🛑 Parando PyMice Web...${NC}\n"

    local stopped=false

    # Parar Backend
    if [ -f "$PID_DIR/backend.pid" ]; then
        PID=$(cat "$PID_DIR/backend.pid")
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}⏹${NC}  Parando Backend (PID: $PID)..."
            kill $PID 2>/dev/null
            stopped=true
        fi
        rm "$PID_DIR/backend.pid"
    fi

    # Parar Frontend
    if [ -f "$PID_DIR/frontend.pid" ]; then
        PID=$(cat "$PID_DIR/frontend.pid")
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}⏹${NC}  Parando Frontend (PID: $PID)..."
            kill $PID 2>/dev/null
            stopped=true
        fi
        rm "$PID_DIR/frontend.pid"
    fi

    # Fallback: matar processos nas portas
    if check_port $BACKEND_PORT; then
        echo -e "${YELLOW}⏹${NC}  Matando processos na porta $BACKEND_PORT..."
        kill $(lsof -t -i:$BACKEND_PORT) 2>/dev/null || true
        stopped=true
    fi

    if check_port $FRONTEND_PORT; then
        echo -e "${YELLOW}⏹${NC}  Matando processos na porta $FRONTEND_PORT..."
        kill $(lsof -t -i:$FRONTEND_PORT) 2>/dev/null || true
        stopped=true
    fi

    if [ "$stopped" = true ]; then
        echo ""
        echo -e "${GREEN}✓ Serviços parados!${NC}"
    else
        echo -e "${YELLOW}⚠${NC}  Nenhum serviço estava rodando"
    fi

    echo ""
}

# Reiniciar serviços
restart_services() {
    stop_services
    sleep 2
    start_services
}

# Ver logs
show_logs() {
    local service=$1
    show_banner

    if [ "$service" = "backend" ]; then
        if [ -f "$LOG_DIR/backend.log" ]; then
            echo -e "${BLUE}📝 Logs do Backend (Ctrl+C para sair)${NC}\n"
            tail -f "$LOG_DIR/backend.log"
        else
            echo -e "${RED}✗${NC} Arquivo de log não encontrado"
            read -p "Pressione Enter para voltar..."
        fi
    elif [ "$service" = "frontend" ]; then
        if [ -f "$LOG_DIR/frontend.log" ]; then
            echo -e "${BLUE}📝 Logs do Frontend (Ctrl+C para sair)${NC}\n"
            tail -f "$LOG_DIR/frontend.log"
        else
            echo -e "${RED}✗${NC} Arquivo de log não encontrado"
            read -p "Pressione Enter para voltar..."
        fi
    fi
}

# Menu interativo
show_menu() {
    while true; do
        show_banner

        echo -e "${GREEN}Escolha uma opção:${NC}\n"
        echo -e "  ${YELLOW}1)${NC} 🚀 Iniciar Serviços (Frontend + Backend)"
        echo -e "  ${YELLOW}2)${NC} 🛑 Parar Serviços"
        echo -e "  ${YELLOW}3)${NC} 🔄 Reiniciar Serviços"
        echo -e "  ${YELLOW}4)${NC} 📊 Ver Status"
        echo -e "  ${YELLOW}5)${NC} 📝 Ver Logs do Backend"
        echo -e "  ${YELLOW}6)${NC} 📝 Ver Logs do Frontend"
        echo -e "  ${YELLOW}7)${NC} 🧹 Limpar Temporários"
        echo -e "  ${YELLOW}0)${NC} ❌ Sair"
        echo ""
        echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
        echo ""

        read -p "Digite a opção: " choice
        echo ""

        case $choice in
            1)
                start_services
                read -p "Pressione Enter para voltar ao menu..."
                ;;
            2)
                stop_services
                read -p "Pressione Enter para voltar ao menu..."
                ;;
            3)
                restart_services
                read -p "Pressione Enter para voltar ao menu..."
                ;;
            4)
                show_status
                read -p "Pressione Enter para voltar ao menu..."
                ;;
            5)
                show_logs "backend"
                ;;
            6)
                show_logs "frontend"
                ;;
            7)
                clean_temporaries
                read -p "Pressione Enter para voltar ao menu..."
                ;;
            0)
                clear
                echo -e "${CYAN}Até logo!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Opção inválida!${NC}"
                sleep 1
                ;;
        esac
    done
}

# Main
case "${1:-}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    clean)
        clean_temporaries
        ;;
    logs)
        if [ -n "$2" ]; then
            show_logs "$2"
        else
            echo -e "${RED}Erro: Especifique backend ou frontend${NC}"
            echo "Uso: ./run.sh logs [backend|frontend]"
            exit 1
        fi
        ;;
    menu)
        show_menu
        ;;
    "")
        show_menu
        ;;
    *)
        echo -e "${RED}Erro: Comando desconhecido '${1}'${NC}"
        echo ""
        echo -e "${GREEN}Comandos disponíveis:${NC}"
        echo "  ./run.sh start            # Iniciar serviços"
        echo "  ./run.sh stop             # Parar serviços"
        echo "  ./run.sh restart          # Reiniciar serviços"
        echo "  ./run.sh status           # Ver status"
        echo "  ./run.sh logs [backend|frontend]  # Ver logs"
        echo "  ./run.sh menu             # Menu interativo"
        echo ""
        exit 1
        ;;
esac

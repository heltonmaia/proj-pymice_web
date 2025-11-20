#!/bin/bash
# PyMice Tracking Panel - Unified Docker Management Script

set -e

BACKEND_PORT=8000
FRONTEND_PORT=5173
DATA_DIR="./backend/temp"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to check if port is in use
check_port() {
    local port=$1
    if ss -tlnp | grep -q ":$port "; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to get process using port
get_port_process() {
    local port=$1
    # Try lsof first
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$pids"
        return 0
    fi

    # Try fuser
    pids=$(fuser $port/tcp 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$pids"
        return 0
    fi

    # Try ss with pid extraction
    pids=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1)
    if [ -n "$pids" ]; then
        echo "$pids"
        return 0
    fi

    return 1
}

# Function to kill process on port
kill_port_process() {
    local port=$1

    # Check if port is actually in use
    if ! check_port $port; then
        echo -e "${GREEN}✓ Port $port is already free${NC}"
        return 0
    fi

    local pids=$(get_port_process $port)

    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Killing process(es) on port $port: $pids${NC}"
        for pid in $pids; do
            # Try to get process name
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "unknown")
            echo -e "  Process: $pname (PID: $pid)"

            if kill $pid 2>/dev/null; then
                echo -e "${GREEN}✓ Killed process $pid${NC}"
            else
                echo -e "${RED}✗ Could not kill process $pid${NC}"
                echo -e "${YELLOW}  Try manually: sudo kill $pid${NC}"
            fi
        done
        sleep 1

        # Check if port is now free
        if ! check_port $port; then
            echo -e "${GREEN}✓ Port $port is now free${NC}"
            return 0
        else
            echo -e "${RED}✗ Port $port is still occupied${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️  Port $port is in use but could not identify the process${NC}"
        echo -e "${CYAN}Possible causes:${NC}"
        echo -e "  - Process running as different user (try: sudo lsof -i :$port)"
        echo -e "  - Docker container holding the port"
        echo -e "  - TIME_WAIT socket (will free automatically in ~60s)"
        echo ""
        read -p "Try to force with sudo fuser? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Running: sudo fuser -k $port/tcp${NC}"
            if sudo fuser -k $port/tcp 2>/dev/null; then
                echo -e "${GREEN}✓ Port freed${NC}"
                sleep 1
                return 0
            else
                echo -e "${RED}✗ Could not free port${NC}"
                return 1
            fi
        fi
        return 1
    fi
}

# Function to free ports
free_ports() {
    clear
    echo -e "${BLUE}🐭 PyMice - Free Ports${NC}"
    echo "=========================================="
    echo ""

    echo -e "${CYAN}Checking ports...${NC}"
    echo ""

    # Check backend port
    echo -n "Backend port $BACKEND_PORT: "
    if check_port $BACKEND_PORT; then
        echo -e "${YELLOW}IN USE${NC}"
        local pids=$(get_port_process $BACKEND_PORT)
        if [ -n "$pids" ]; then
            echo "  Process(es): $pids"
        fi
    else
        echo -e "${GREEN}FREE${NC}"
    fi

    # Check frontend port
    echo -n "Frontend port $FRONTEND_PORT: "
    if check_port $FRONTEND_PORT; then
        echo -e "${YELLOW}IN USE${NC}"
        local pids=$(get_port_process $FRONTEND_PORT)
        if [ -n "$pids" ]; then
            echo "  Process(es): $pids"
        fi
    else
        echo -e "${GREEN}FREE${NC}"
    fi

    echo ""
    echo "Options:"
    echo "  1) Free backend port ($BACKEND_PORT)"
    echo "  2) Free frontend port ($FRONTEND_PORT)"
    echo "  3) Free both ports"
    echo "  4) Back to main menu"
    echo ""
    read -p "Enter choice [1-4]: " choice

    case $choice in
        1)
            kill_port_process $BACKEND_PORT
            ;;
        2)
            kill_port_process $FRONTEND_PORT
            ;;
        3)
            kill_port_process $BACKEND_PORT
            kill_port_process $FRONTEND_PORT
            ;;
        4)
            return
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            ;;
    esac

    echo ""
    read -p "Press Enter to continue..."
}

# Function to create data directories
create_data_dirs() {
    echo -e "${CYAN}Creating data directories in $DATA_DIR...${NC}"
    mkdir -p "$DATA_DIR/videos"
    mkdir -p "$DATA_DIR/models"
    mkdir -p "$DATA_DIR/tracking"
    mkdir -p "$DATA_DIR/roi_templates"
    echo -e "${GREEN}✓ Data directories created${NC}"
}

# Function to start services
start_services() {
    clear
    echo -e "${BLUE}🐭 PyMice - Start Services${NC}"
    echo "=========================================="
    echo ""

    # Check Docker installation
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed${NC}"
        echo "   Visit: https://docs.docker.com/get-docker/"
        read -p "Press Enter to continue..."
        return
    fi

    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Docker Compose is not installed${NC}"
        echo "   Visit: https://docs.docker.com/compose/install/"
        read -p "Press Enter to continue..."
        return
    fi

    # Check for existing containers
    if docker ps -a | grep -q "pymice-"; then
        echo -e "${YELLOW}⚠️  Found existing PyMice containers:${NC}"
        docker ps -a | grep "pymice-"
        echo ""
        read -p "Stop and remove these containers? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose down 2>/dev/null || true
            docker-compose -f docker-compose.gpu.yml down 2>/dev/null || true
            echo -e "${GREEN}✓ Containers stopped${NC}"
        fi
    fi

    # Check ports
    echo ""
    echo -e "${CYAN}Checking ports...${NC}"
    local ports_blocked=false

    if check_port $BACKEND_PORT; then
        echo -e "${YELLOW}⚠️  Backend port $BACKEND_PORT is in use${NC}"
        ports_blocked=true
    fi

    if check_port $FRONTEND_PORT; then
        echo -e "${YELLOW}⚠️  Frontend port $FRONTEND_PORT is in use${NC}"
        ports_blocked=true
    fi

    if [ "$ports_blocked" = true ]; then
        echo ""
        read -p "Free ports automatically? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill_port_process $BACKEND_PORT || true
            kill_port_process $FRONTEND_PORT || true
        else
            echo -e "${RED}Cannot start with ports occupied${NC}"
            read -p "Press Enter to continue..."
            return
        fi
    fi

    # Create data directories
    echo ""
    create_data_dirs

    # Ask for GPU or CPU mode
    echo ""
    echo "Select mode:"
    echo "  1) CPU mode (works everywhere)"
    echo "  2) GPU mode (requires NVIDIA GPU + nvidia-docker)"
    read -p "Enter choice [1-2]: " mode

    if [ "$mode" == "2" ]; then
        # Check for nvidia-docker
        if ! docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
            echo -e "${RED}❌ NVIDIA Docker runtime not available${NC}"
            echo "   Install nvidia-docker2: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            read -p "Press Enter to continue..."
            return
        fi

        echo ""
        echo -e "${GREEN}🎮 Starting in GPU mode...${NC}"
        docker-compose -f docker-compose.gpu.yml up --build -d
    else
        echo ""
        echo -e "${GREEN}💻 Starting in CPU mode...${NC}"
        docker-compose up --build -d
    fi

    echo ""
    echo -e "${GREEN}✅ PyMice Tracking Panel is starting!${NC}"
    echo ""
    echo "   Frontend:    http://localhost:$FRONTEND_PORT"
    echo "   Backend API: http://localhost:$BACKEND_PORT"
    echo "   API Docs:    http://localhost:$BACKEND_PORT/docs"
    echo ""
    read -p "Press Enter to continue..."
}

# Function to stop services
stop_services() {
    clear
    echo -e "${BLUE}🐭 PyMice - Stop Services${NC}"
    echo "=========================================="
    echo ""

    echo -e "${YELLOW}🛑 Stopping PyMice Tracking Panel...${NC}"
    docker-compose down 2>/dev/null || true
    docker-compose -f docker-compose.gpu.yml down 2>/dev/null || true
    echo -e "${GREEN}✅ PyMice Tracking Panel stopped${NC}"
    echo ""
    read -p "Press Enter to continue..."
}

# Function to show status
show_status() {
    clear
    echo -e "${BLUE}🐭 PyMice - Status${NC}"
    echo "=========================================="
    echo ""

    echo -e "${CYAN}📊 Container Status:${NC}"
    if docker ps -a | grep -q "pymice-"; then
        docker ps -a | grep "pymice-" | awk '{printf "%-20s %-15s %-20s\n", $2, $7, $1}' | head -1
        docker ps -a | grep "pymice-"
    else
        echo "No PyMice containers found"
    fi

    echo ""
    echo -e "${CYAN}🔌 Port Status:${NC}"
    echo -n "Backend port $BACKEND_PORT:  "
    if check_port $BACKEND_PORT; then
        echo -e "${YELLOW}IN USE${NC}"
    else
        echo -e "${GREEN}FREE${NC}"
    fi

    echo -n "Frontend port $FRONTEND_PORT: "
    if check_port $FRONTEND_PORT; then
        echo -e "${YELLOW}IN USE${NC}"
    else
        echo -e "${GREEN}FREE${NC}"
    fi

    echo ""
    echo -e "${CYAN}💾 Data Directory:${NC}"
    if [ -d "$DATA_DIR" ]; then
        echo -e "${GREEN}✓${NC} $DATA_DIR"
        du -sh "$DATA_DIR" 2>/dev/null || echo "  (size unknown)"
    else
        echo -e "${RED}✗${NC} $DATA_DIR (not created)"
    fi

    echo ""
    read -p "Press Enter to continue..."
}

# Function to show logs
show_logs() {
    clear
    echo -e "${BLUE}🐭 PyMice - Logs${NC}"
    echo "=========================================="
    echo ""
    echo "Which logs do you want to see?"
    echo "  1) All services"
    echo "  2) Backend only"
    echo "  3) Frontend only"
    echo "  4) Back to main menu"
    echo ""
    read -p "Enter choice [1-4]: " choice

    case $choice in
        1)
            docker-compose logs -f
            ;;
        2)
            docker-compose logs -f backend
            ;;
        3)
            docker-compose logs -f frontend
            ;;
        4)
            return
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            read -p "Press Enter to continue..."
            ;;
    esac
}

# Function to show main menu
show_menu() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  🐭 PyMice Tracking Panel - Manager  ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo "  1) 🚀 Start services"
    echo "  2) 🛑 Stop services"
    echo "  3) 🔄 Restart services"
    echo "  4) 📊 Show status"
    echo "  5) 📋 View logs"
    echo "  6) 🔓 Free ports"
    echo "  7) 🚪 Exit"
    echo ""
    read -p "Enter your choice [1-7]: " choice

    case $choice in
        1)
            start_services
            ;;
        2)
            stop_services
            ;;
        3)
            stop_services
            sleep 2
            start_services
            ;;
        4)
            show_status
            ;;
        5)
            show_logs
            ;;
        6)
            free_ports
            ;;
        7)
            clear
            echo -e "${GREEN}👋 Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            sleep 1
            ;;
    esac
}

# Main loop - if no arguments, show menu
if [ $# -eq 0 ]; then
    while true; do
        show_menu
    done
else
    # Support command line arguments for automation
    case "$1" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            sleep 2
            start_services
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        free-ports)
            free_ports
            ;;
        *)
            echo "Usage: $0 [start|stop|restart|status|logs|free-ports]"
            echo "Or run without arguments for interactive menu"
            exit 1
            ;;
    esac
fi

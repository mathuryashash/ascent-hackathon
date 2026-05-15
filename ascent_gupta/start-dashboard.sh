#!/bin/bash
# Chimera Dashboard Startup Script (Linux/macOS)
# This script starts both the backend MCP server and frontend dashboard

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_SERVICE="$PROJECT_ROOT/services/brain/main.py"
GATEWAY_UI="$PROJECT_ROOT/services/gateway_ui/public"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Project Chimera - Dashboard Launcher               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ Python detected: $PYTHON_VERSION"
echo ""

# Start Brain Service (Backend MCP Server)
echo "🧠 Starting Brain Service (MCP Server on port 8000)..."
echo "   Running: uvicorn services.brain.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""

cd "$PROJECT_ROOT"
python3 -m uvicorn services.brain.main:app --host 0.0.0.0 --port 8000 --reload &
BRAIN_PID=$!

echo "✅ Brain Service PID: $BRAIN_PID"
echo "   Wait for: 'Application startup complete'"
echo ""

# Wait for backend to start
sleep 3

# Start Frontend Dashboard
echo "🎨 Starting Frontend Dashboard (port 3000)..."
echo "   Running: python3 -m http.server 3000"
echo ""

cd "$GATEWAY_UI"
python3 -m http.server 3000 &
GATEWAY_PID=$!

echo "✅ Frontend Dashboard PID: $GATEWAY_PID"
echo "   URL: http://localhost:3000"
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              🚀 Services Started Successfully!              ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║  Backend  (MCP Server): http://localhost:8000/health     ║"
echo "║  Frontend (Dashboard):  http://localhost:3000            ║"
echo "║                                                            ║"
echo "║  📖 Documentation: Read DASHBOARD_SETUP.md                ║"
echo "║  🧪 Test Alert: POST http://localhost:8000/webhook      ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

echo "Press Ctrl+C to stop services..."
echo ""

# Handle cleanup
trap "kill $BRAIN_PID $GATEWAY_PID" EXIT INT TERM

# Wait for processes
wait

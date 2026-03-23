#!/bin/bash
set -e

PROJECT_DIR="/home/kalpa/.gemini/antigravity/scratch/opcua-simulator"

echo "Setting up OPC UA Simulator..."

cd $PROJECT_DIR

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

SERVICE_NAME="opcua-simulator.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

echo "Installing systemd service (requires sudo)..."
sudo cp $PROJECT_DIR/$SERVICE_NAME $SERVICE_PATH
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
fi
FLASK_PORT=${FLASK_PORT:-8080}
OPC_UA_PORT=${OPC_UA_PORT:-4840}

echo "--------------------------------------------------------"
echo "OPC UA Simulator installed and started successfully!"
echo "Check status:"
echo "sudo systemctl status opcua-simulator"
echo ""
echo "Web GUI: http://localhost:${FLASK_PORT}"
echo "OPC UA Endpoint: opc.tcp://localhost:${OPC_UA_PORT}/freeopcua/server/"

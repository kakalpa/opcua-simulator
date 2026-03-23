# OPC UA Simulator

A lightweight, configuration-driven OPC UA simulator with a real-time web dashboard.

This digital twin environment allows you to emulate complex hierarchical PLC tag structures, deploy mathematical node simulation profiles, inject logical cause-and-effect rules, and provision or delete nodes dynamically—all from an intuitive graphical web interface.

## Features

- **Dynamic Node Management**: Add, edit, and delete OPC UA nodes dynamically from the web interface without restarting the server or breaking connected SCADA systems.
- **Simulation Profiles**: Emulate sensor behaviors using built-in math profiles:
  - `Sine Wave`
  - `Tangent Wave`
  - `Random Walk`
  - `Constant Bias`
- **Rule Engine**: Define trigger-and-effect rules that allow components to react to each other logically.
- **Dashboard UI**: Real-time graphical visualization of tags, node structures, and live alarms.

## Prerequisites

- **Python 3.8+**
- Git (optional, for cloning)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kakalpa/opcua-simulator.git
   cd opcua-simulator
   ```

2. **Automated Install:**
   An installation script is provided to set up the virtual environment, install dependencies, and configure the system.
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

3. **Environment Configuration:**
   The installation script generates a `.env` file where you can define your custom ports. If you bypassed the script, you can create the file manually:
   ```env
   # .env
   FLASK_PORT=8080
   OPC_UA_PORT=4840
   ```

## Usage

Start the simulator:
```bash
source venv/bin/activate
python app.py
```

- Access the **Simulator Dashboard** in your browser at: `http://localhost:<FLASK_PORT>` (default: 8080).
- Connect your **SCADA / OPC UA Client** to: `opc.tcp://0.0.0.0:<OPC_UA_PORT>/freeopcua/server/` (default: 4840).

## Systemd Service

If you wish to run the simulator persistently on Linux, a `opcua-simulator.service` systemd file is provided. Edit the path inside the file, place it in `/etc/systemd/system/`, and enable it via `systemctl enable opcua-simulator`.

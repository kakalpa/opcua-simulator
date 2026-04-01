# OPC UA Simulator

A lightweight, configuration-driven OPC UA simulator with a real-time web dashboard.

This digital twin environment allows you to emulate complex hierarchical PLC tag structures, deploy mathematical node simulation profiles, inject logical cause-and-effect rules, and provision or delete nodes dynamically—all from an intuitive graphical web interface.

## Highlights & New Features

- **SQLite Persistent State**: All nodes and interactions are stored in a robust local `opcua_config.db` database, ensuring that manual SCADA interactions (like moving a slider) persist flawlessly through server restarts without being overwritten by background engines.
- **Dynamic Node Management**: Add, edit, and delete OPC UA nodes dynamically from the web interface without restarting the server or breaking connected SCADA systems.
- **Advanced Physics Simulation Profiles**: Emulate complex environments using:
  - `Sine Wave` & `Cosine Wave`
  - `Tangent Wave`
  - `Random Walk`
  - `Constant Bias`
  - `Thermal` (includes drift, gain, and configurable loop wrapping—ideal for modeling **conveyor belts** or continuous flow!).
- **Rule Engine & Node Relationships**: Define complex logic rules directly from the GUI to link node behaviors:
  - **Causal Logic**: Trigger simulation changes on one node (Effect) based on the state or value of another (Cause).
  - **Range-based Logic**: Use the `between` operator to trigger effects when a sensor enters a specific zone (e.g., configuring *BeltWeight* values depending on where a product is on the *BeltPosition*).
  - **Multiplier Logic**: Link an analog slider (e.g., a Valve or MotorSpeed) to act as a direct percentage multiplier on another simulation's progression (e.g., modifying Pressure or Belt Positioning).
  - **Fail-safe Logic**: Chain rules to kill switches if thermal models exceed safe parameters (e.g., turning off the `Status` switch when `MotorTemp` exceeds 120°C).

## Important SCADA Integration Note

> ⚠️ **Node ID Shifting**: When dynamically adding new nodes through the web interface, the OPC UA server auto-increments the internal numeric `NodeId` assignments for all sequential items in that namespace. 
> 
> *If you register a gauge in your SCADA visualization panel using an explicit numeric ID (e.g., `ns=2;i=15`), and then later add a new folder of nodes to the simulator, that specific tag may shift (e.g., to `ns=2;i=23`). Ensure you regularly map your SCADA clients via `BrowseName` identifiers or strictly review your Node IDs when updating the architecture.*

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

- Access the **Simulator Dashboard UI** in your browser at: `http://localhost:<FLASK_PORT>` (default: 8080).
- Connect your **SCADA / OPC UA Client** to: `opc.tcp://0.0.0.0:<OPC_UA_PORT>/freeopcua/server/` (default: 4840).

## Background Daemon / Systemd Service

If you wish to run the simulator persistently as a background industrial service on Linux, you can utilize the included systemd template configuration. 

**Quick Installation:**
```bash
# Link the unit file to systemd's directory
sudo ln -s /path/to/opcua-simulator/opcua-simulator.service /etc/systemd/system/

# Reload daemon and execute
sudo systemctl daemon-reload
sudo systemctl enable opcua-simulator
sudo systemctl start opcua-simulator
```
*(Application logs are piped automatically to `simulator.log` in the project root folder).*

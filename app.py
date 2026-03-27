import asyncio
import logging
import threading
import random
import math
import time
import json
import os
from dotenv import load_dotenv
from asyncua import Server, ua
from flask import Flask, render_template, jsonify, request

load_dotenv()
FLASK_PORT = int(os.environ.get('FLASK_PORT', 8080))
OPC_UA_PORT = int(os.environ.get('OPC_UA_PORT', 4840))

# Load config relative to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

app = Flask(__name__, 
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
else:
    config = {"hierarchy": {}, "rules": [], "alarms": []}

# Ensure rules and alarms are initialized correctly
if "rules" not in config: config["rules"] = []
if "alarms" not in config: config["alarms"] = []

nodes = {} # Key: "Folder/NodeName"
folders_cache = {} # Key: "Folder/Path"
alarms_config = config["alarms"]
rules_config = config["rules"]

loop = asyncio.new_event_loop()
start_time = time.time()
server_obj = None
namespace_idx = None
my_evgen = None

async def build_hierarchy(parent_obj, structure, current_path=""):
    for name, data in structure.items():
        path = f"{current_path}/{name}" if current_path else name
        
        if data["type"] == "folder":
            folder = await parent_obj.add_folder(namespace_idx, name)
            folders_cache[path] = folder
            await build_hierarchy(folder, data.get("children", {}), path)
        else:
            datatype_str = data.get("datatype", "Double")
            ua_type = getattr(ua.VariantType, datatype_str, ua.VariantType.Double)
            
            init_val = data.get("value", 0.0)
            if data["type"] == "switch":
                init_val = data.get("value", False)
                ua_type = ua.VariantType.Boolean
                
            var_node = await parent_obj.add_variable(namespace_idx, name, ua.Variant(init_val, ua_type))
            await var_node.set_writable()
            
            payload = {
                "node": var_node,
                "type": data["type"],
                "unit": data.get("unit", ""),
                "sim": data.get("sim", {}),
                "value": init_val,
                "datatype": ua_type,
                "alarm_state": "NORMAL"
            }
            if data["type"] == "slider":
                payload["min"] = data.get("min", 0.0)
                payload["max"] = data.get("max", 100.0)
                
            nodes[path] = payload

def evaluate_rules_logic():
    for path, data in nodes.items():
        data["multiplier"] = 1.0

    # Sort rules by priority (default 0). Higher priority runs last to override.
    sorted_rules = sorted(rules_config, key=lambda x: x.get("priority", 0))

    for rule in sorted_rules:
        cause = rule.get("cause")
        if not cause or cause["node"] not in nodes:
            continue
            
        cause_val = nodes[cause["node"]]["value"]
        
        if cause.get("operator") == "multiplier":
            target = cause.get("target")
            if target in nodes:
                nodes[target]["multiplier"] = float(cause_val) / 100.0
            continue
            
        condition = cause.get("condition")
        target_val = cause.get("value")
        triggered = False
        
        if condition == "==": triggered = (cause_val == target_val)
        elif condition == "!=": triggered = (cause_val != target_val)
        elif condition == ">": triggered = (cause_val > target_val)
        elif condition == "<": triggered = (cause_val < target_val)
        elif condition == ">=": triggered = (cause_val >= target_val)
        elif condition == "<=": triggered = (cause_val <= target_val)
            
        if triggered:
            effect = rule.get("effect")
            if not effect or effect["node"] not in nodes:
                continue
            effect_path = effect["node"]
            
            if effect["action"] == "set_sim":
                current_sim = nodes[effect_path].get("sim", {})
                new_sim = effect["sim"]
                # Only update if the simulation profile has actually changed
                if current_sim.get("type") != new_sim.get("type") or \
                   current_sim.get("min") != new_sim.get("min") or \
                   current_sim.get("max") != new_sim.get("max") or \
                   current_sim.get("value") != new_sim.get("value"):
                    nodes[effect_path]["sim"] = new_sim.copy()

async def opcua_server_task():
    global server_obj, namespace_idx, my_evgen
    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://0.0.0.0:{OPC_UA_PORT}/freeopcua/server/")
    server.set_server_name("Advanced Python OPC UA Simulator")

    uri = "http://simulator.local"
    namespace_idx = await server.register_namespace(uri)
    objects = server.nodes.objects
    server_obj = await objects.add_object(namespace_idx, "SimulatorFactory")
    
    my_evgen = await server.get_event_generator()
    
    await build_hierarchy(server_obj, config.get("hierarchy", {}), "")

    logging.info(f"Starting OPC UA Server on opc.tcp://0.0.0.0:{OPC_UA_PORT}/freeopcua/server/")
    
    # Retry loop for port binding (handle slow OS release)
    retries = 5
    while retries > 0:
        try:
            async with server:
                while True:
                    await asyncio.sleep(1.0)
                    t = time.time() - start_time
                    
                    # Step 1: Read inputs
                    for path in list(nodes.keys()):
                        try:
                            data = nodes.get(path)
                            if not data or "node" not in data: continue
                            val = await data["node"].read_value()
                            data["value"] = val
                        except Exception as e:
                            logging.error(f"Error reading node {path}: {e}")
                    
                    # Step 2: Evaluate logic rules
                    try:
                        evaluate_rules_logic()
                    except Exception as e:
                        logging.error(f"Error evaluating rules: {e}")
                    
                    # Step 3: Run Math Simulations
                    for path in list(nodes.keys()):
                        try:
                            data = nodes.get(path)
                            if not data or data["type"] != "sensor" or "sim" not in data: 
                                continue
                                
                            sim = data["sim"]
                            new_val = None
                            multiplier = data.get("multiplier", 1.0)
                            
                            if sim.get("type") == "sin":
                                amplitude = (sim.get("max", 100.0) - sim.get("min", 0.0)) / 2.0
                                base = sim.get("min", 0.0) + amplitude
                                period = sim.get("period", 60.0) or 60.0
                                new_val = (base + (amplitude * math.sin(t * 2 * math.pi / period))) * multiplier
                            elif sim.get("type") == "random":
                                current = sim.get("current", sim.get("min", 0.0))
                                step = (sim.get("max", 100.0) - sim.get("min", 0.0)) * 0.1
                                current += random.uniform(-step, step)
                                current = max(sim.get("min", 0.0), min(current, sim.get("max", 100.0)))
                                sim["current"] = current
                                new_val = current * multiplier
                            elif sim.get("type") == "constant":
                                new_val = sim.get("value", data.get("value", 0.0)) * multiplier
                            elif sim.get("type") == "tan":
                                period = sim.get("period", 60.0) or 60.0
                                new_val = (math.tan(t * math.pi / period)) * multiplier
                                # Clamp tan to avoid infinity
                                new_val = max(-1000.0, min(new_val, 1000.0))

                            if new_val is not None:
                                await data["node"].write_value(ua.Variant(round(new_val, 3), data["datatype"]))
                                data["value"] = round(new_val, 3)
                        except Exception as e:
                            logging.error(f"Error simulating node {path}: {e}")

                    # Step 4: Check Alarms
                    for alarm in alarms_config:
                        path = alarm["node"]
                        if path in nodes:
                            val = nodes[path]["value"]
                            if val > alarm.get("limit_high", float('inf')):
                                if nodes[path]["alarm_state"] != "HIGH":
                                    nodes[path]["alarm_state"] = "HIGH"
                                    await my_evgen.trigger(message=f"High limit exceeded on {path}")
                            elif val < alarm.get("limit_low", float('-inf')):
                                if nodes[path]["alarm_state"] != "LOW":
                                    nodes[path]["alarm_state"] = "LOW"
                                    await my_evgen.trigger(message=f"Low limit exceeded on {path}")
                            else:
                                nodes[path]["alarm_state"] = "NORMAL"
            break # Exit retry loop on successful startup and normal exit (unlikely)
        except Exception as e:
            logging.error(f"Failed to start OPC UA Server (retrying in 2s): {e}")
            await asyncio.sleep(2.0)
            retries -= 1

def run_opcua_server():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(opcua_server_task())

opc_thread = threading.Thread(target=run_opcua_server, daemon=True)
opc_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    if not namespace_idx:
        return jsonify({"error": "OPC UA Server not ready"}), 503
        
    try:
        results = {}
        for path in list(nodes.keys()):
            if path not in nodes: continue
            data = nodes[path]
            payload = {
                "value": data["value"],
                "unit": data["unit"],
                "type": data["type"],
                "sim_type": data.get("sim", {}).get("type", "none"),
                "alarm_state": data.get("alarm_state", "NORMAL")
            }
            if data["type"] == "slider":
                payload["min"] = data.get("min", 0.0)
                payload["max"] = data.get("max", 100.0)
            results[path] = payload
            
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/set_value', methods=['POST'])
def set_value():
    data = request.json
    path = data.get("name") 
    val = data.get("value")
    
    if path in nodes and "node" in nodes[path]:
        node_payload = nodes[path]
        try:
            if node_payload["type"] == "switch":
                val = bool(val)
                ua_val = ua.Variant(val, ua.VariantType.Boolean)
            else:
                val = float(val)
                ua_val = ua.Variant(val, node_payload["datatype"])
                
            asyncio.run_coroutine_threadsafe(
                node_payload["node"].write_value(ua_val), loop
            )
            node_payload["value"] = val
            return jsonify({"success": True})
        except ValueError:
             return jsonify({"success": False, "error": "Invalid value format"}), 400
    return jsonify({"success": False, "error": "Node not ready"}), 404

@app.route('/api/add_node', methods=['POST'])
def add_node():
    data = request.json
    name = data.get("name")
    folder_path = data.get("folder", "")
    node_type = data.get("node_type", "sensor")
    unit = data.get("unit", "")
    
    if not name: return jsonify({"success": False, "error": "Name required"}), 400
    
    # Strip leading/trailing slashes
    folder_path = folder_path.strip("/")
    full_path = f"{folder_path}/{name}" if folder_path else name
    
    if full_path in nodes: return jsonify({"success": False, "error": "Node already exists"}), 400
    
    try:
        min_val = float(data.get("min", 0.0))
        max_val = float(data.get("max", 100.0))
        period_val = float(data.get("period", 60.0))
        sim_type = data.get("sim_type", "constant")
        init_val = float(data.get("value", 0.0)) if node_type != "switch" else bool(data.get("value", False))
    except ValueError:
        return jsonify({"success": False, "error": "Numeric fields must be valid numbers"}), 400

    # Build the config structure addition
    parts = folder_path.split("/") if folder_path else []
    current_level = config["hierarchy"]
    for p in parts:
        if p not in current_level:
            current_level[p] = {"type": "folder", "children": {}}
        current_level = current_level[p].get("children", {})
        
    node_data = {
        "type": node_type,
        "value": init_val
    }
    
    if node_type == "switch":
        node_data["datatype"] = "Boolean"
    else:
        node_data["datatype"] = "Double"
        node_data["unit"] = unit
        
    if node_type == "sensor":
        node_data["sim"] = {
            "type": sim_type, "min": min_val, "max": max_val, "period": period_val, "current": init_val
        }
    elif node_type == "slider":
        node_data["min"] = min_val
        node_data["max"] = max_val

    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503

    async def _inject_node():
        parent_obj = server_obj
        current_path = ""
        for p in parts:
            current_path = f"{current_path}/{p}" if current_path else p
            if current_path not in folders_cache:
                folder = await parent_obj.add_folder(namespace_idx, p)
                folders_cache[current_path] = folder
                parent_obj = folder
            else:
                parent_obj = folders_cache[current_path]
                
        # Now add the variable
        ua_type = getattr(ua.VariantType, node_data["datatype"])
        var_node = await parent_obj.add_variable(namespace_idx, name, ua.Variant(init_val, ua_type))
        await var_node.set_writable()
        
        payload = {
            "node": var_node,
            "type": node_data["type"],
            "unit": node_data.get("unit", ""),
            "sim": node_data.get("sim", {}),
            "value": init_val,
            "datatype": ua_type,
            "alarm_state": "NORMAL"
        }
        if node_type == "slider":
            payload["min"] = min_val
            payload["max"] = max_val
            
        nodes[full_path] = payload

    future = asyncio.run_coroutine_threadsafe(_inject_node(), loop)
    try:
        future.result(timeout=2.0)
        
        # Injection succeeded, save to config
        current_level[name] = node_data
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

DEMO_DATA = {
    "type": "folder",
    "children": {
        "DemonstrationPlant": {
            "type": "folder",
            "children": {
                "CoolingTower": {
                    "type": "folder",
                    "children": {
                        "WaterTemp": {
                            "type": "sensor", "datatype": "Double", "unit": "°C",
                            "sim": {"type": "sin", "min": 20.0, "max": 40.0, "period": 15.0}
                        },
                        "FanStatus": {
                           "type": "switch", "datatype": "Boolean", "value": False
                        }
                    }
                },
                "MainBoiler": {
                     "type": "folder",
                     "children": {
                         "Pressure": {
                            "type": "sensor", "datatype": "Double", "unit": "Bar",
                            "sim": {"type": "random", "min": 1.0, "max": 2.5}
                         },
                         "SafetyValve": {
                             "type": "slider", "datatype": "Double", "unit": "%",
                             "min": 0.0, "max": 100.0, "value": 0.0
                         }
                     }
                }
            }
        }
    }
}

DEMO_RULES = [
    {
      "cause": { "node": "DemonstrationPlant/CoolingTower/FanStatus", "condition": "==", "value": True },
      "effect": { "node": "DemonstrationPlant/CoolingTower/WaterTemp", "action": "set_sim", "sim": { "type": "sin", "min": 10.0, "max": 20.0, "period": 10.0 } }
    },
    {
      "cause": { "node": "DemonstrationPlant/CoolingTower/FanStatus", "condition": "==", "value": False },
      "effect": { "node": "DemonstrationPlant/CoolingTower/WaterTemp", "action": "set_sim", "sim": { "type": "sin", "min": 20.0, "max": 40.0, "period": 15.0 } }
    },
    {
      "cause": { "node": "DemonstrationPlant/MainBoiler/SafetyValve", "operator": "multiplier", "target": "DemonstrationPlant/MainBoiler/Pressure" }
    }
]

DEMO_ALARMS = [
    { "node": "DemonstrationPlant/CoolingTower/WaterTemp", "limit_high": 35.0 }
]
@app.route('/api/edit_node', methods=['POST'])
def edit_node():
    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503

    data = request.json
    path = data.get("path")
    
    if path not in nodes:
        return jsonify({"success": False, "error": "Node not found"}), 404
        
    parts = path.split('/')
    name = parts[-1]
    
    current_level = config["hierarchy"]
    folder_level = current_level
    for p in parts[:-1]:
        if p not in current_level:
            return jsonify({"success": False, "error": "Hierarchy corrupted"}), 500
        current_level = current_level[p]
        if "children" not in current_level:
            return jsonify({"success": False, "error": "Folder hierarchy broken"}), 500
        folder_level = current_level["children"]
        current_level = folder_level
        
    if name not in folder_level:
        return jsonify({"success": False, "error": "Node not in config"}), 500
        
    node_config = folder_level[name]
    
    if "unit" in data:
        node_config["unit"] = data["unit"]
        nodes[path]["unit"] = data["unit"]
        
    if "min" in data and data["min"] != "":
        node_config["min"] = float(data["min"])
        nodes[path]["min"] = float(data["min"])
        
    if "max" in data and data["max"] != "":
        node_config["max"] = float(data["max"])
        nodes[path]["max"] = float(data["max"])
        
    if "sim_type" in data:
        sim_type = data["sim_type"]
        period = data.get("period", 10.0)
        try:
            period = float(period)
        except ValueError:
            period = 10.0
            
        node_sim = {"type": sim_type, "period": period}
        
        # Preserve min/max/current for random walk etc if they exist
        if "sim" in node_config:
            if "min" in node_config["sim"]: node_sim["min"] = node_config["sim"]["min"]
            if "max" in node_config["sim"]: node_sim["max"] = node_config["sim"]["max"]
            if "current" in node_config["sim"]: node_sim["current"] = node_config["sim"]["current"]
            
        # Or fetch from data
        if "min" in data and data["min"] != "": node_sim["min"] = float(data["min"])
        if "max" in data and data["max"] != "": node_sim["max"] = float(data["max"])
        if "value" in data and data["value"] != "": node_sim["value"] = float(data["value"])
            
        node_config["sim"] = node_sim
        nodes[path]["sim"] = node_sim
        
        # Immediate value assignment for constant types
        if sim_type == "constant" and "value" in node_sim:
            nodes[path]["value"] = node_sim["value"]
            
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
        
    return jsonify({"success": True})

@app.route('/api/delete_node', methods=['POST'])
def delete_node():
    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503

    data = request.json
    path = data.get("path")
    
    if path not in nodes:
        return jsonify({"success": False, "error": "Node not found"}), 404
        
    parts = path.split('/')
    name = parts[-1]
    
    current_level = config["hierarchy"]
    folder_level = current_level
    for p in parts[:-1]:
        if p not in current_level:
            return jsonify({"success": False, "error": "Hierarchy corrupted"}), 500
        current_level = current_level[p]
        if "children" not in current_level:
            return jsonify({"success": False, "error": "Folder hierarchy broken"}), 500
        folder_level = current_level["children"]
        current_level = folder_level
        
    if name not in folder_level:
        return jsonify({"success": False, "error": "Node not in config"}), 500
        
    del folder_level[name]
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
        
    del nodes[path]
    return jsonify({"success": True})

@app.route('/api/rules', methods=['GET'])
def get_rules():
    return jsonify(rules_config)

@app.route('/api/add_rule', methods=['POST'])
def add_rule():
    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503
        
    data = request.json
    new_rule = data.get("rule")
    if not new_rule:
        return jsonify({"success": False, "error": "Rule data missing"}), 400
        
    if "rules" not in config:
        config["rules"] = []
    
    config["rules"].append(new_rule)
    if rules_config is not config["rules"]:
        rules_config.append(new_rule)
        
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
        
    return jsonify({"success": True})

@app.route('/api/delete_rule', methods=['POST'])
def delete_rule():
    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503
        
    data = request.json
    index = data.get("index")
    if index is None or index < 0 or index >= len(rules_config):
        return jsonify({"success": False, "error": "Invalid rule index"}), 400
        
    if "rules" in config and index < len(config["rules"]):
        config["rules"].pop(index)
    if rules_config is not config.get("rules"):
        rules_config.pop(index)
        
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
        
    return jsonify({"success": True})

@app.route('/api/update_rules', methods=['POST'])
def update_rules():
    global rules_config
    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503
        
    data = request.json
    new_rules = data.get("rules")
    if new_rules is None:
        return jsonify({"success": False, "error": "Rules list missing"}), 400
        
    # Global replacement of rules in config
    config["rules"] = new_rules
    
    # Update the live reference as well (shared with simulation loop)
    rules_config[:] = new_rules
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
        
    return jsonify({"success": True})


@app.route('/api/load_demo', methods=['POST'])
def load_demo():
    if server_obj is None or namespace_idx is None:
        return jsonify({"success": False, "error": "Server not fully initialized"}), 503

    if "DemonstrationPlant" in config["hierarchy"]:
        return jsonify({"success": False, "error": "Demo plant is already loaded!"}), 400
        
    async def _inject_demo():
        demo_structure = {"DemonstrationPlant": DEMO_DATA["children"]["DemonstrationPlant"]}
        await build_hierarchy(server_obj, demo_structure, "")

    future = asyncio.run_coroutine_threadsafe(_inject_demo(), loop)
    try:
        future.result(timeout=5.0)
        
        # Injection succeeded, save to config
        config["hierarchy"]["DemonstrationPlant"] = DEMO_DATA["children"]["DemonstrationPlant"]
        
        # Avoid duplication if rules/alarms_config are the same objects as config lists
        config["rules"].extend(DEMO_RULES)
        config["alarms"].extend(DEMO_ALARMS)
        
        # If they were somehow already the same list, we don't need to extend twice.
        # But we already did extend config["rules"] which IS rules_config.
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=True, use_reloader=False)

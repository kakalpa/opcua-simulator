import sqlite3
import json
import os
import shutil
import logging

DB_FILE = "opcua_config.db"
CONFIG_FILE = "config.json"

def get_connection():
    # Use check_same_thread=False since we might hit DB from multiple threads (e.g. Flask vs Asyncio)
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS nodes (
        path TEXT PRIMARY KEY,
        name TEXT,
        parent_path TEXT,
        is_folder BOOLEAN,
        config TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_json TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS alarms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alarm_json TEXT
    )''')
    conn.commit()
    conn.close()

def migrate_if_needed():
    if not os.path.exists(DB_FILE) and os.path.exists(CONFIG_FILE):
        logging.info("Migrating config.json to SQLite database...")
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        
        init_db()
        conn = get_connection()
        c = conn.cursor()
        
        def traverse(d, parent_path=""):
            for name, node_data in d.items():
                path = f"{parent_path}/{name}" if parent_path else name
                is_folder = node_data.get("type", "") == "folder"
                
                # Copy node_data without children to store as config
                config_data = {k: v for k, v in node_data.items() if k != "children"}
                
                c.execute('''INSERT OR REPLACE INTO nodes (path, name, parent_path, is_folder, config)
                           VALUES (?, ?, ?, ?, ?)''',
                        (path, name, parent_path, is_folder, json.dumps(config_data)))
                
                if is_folder and "children" in node_data:
                    traverse(node_data["children"], path)
                    
        traverse(data.get("hierarchy", {}))
        
        for rule in data.get("rules", []):
            c.execute('INSERT INTO rules (rule_json) VALUES (?)', (json.dumps(rule),))
            
        for alarm in data.get("alarms", []):
            c.execute('INSERT INTO alarms (alarm_json) VALUES (?)', (json.dumps(alarm),))
            
        conn.commit()
        conn.close()
        
        # Backup the old config
        shutil.move(CONFIG_FILE, CONFIG_FILE + ".bak")
        logging.info("Migration complete. Original config.json backed up as config.json.bak")
    else:
        init_db()

def get_hierarchy():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT path, name, parent_path, is_folder, config FROM nodes')
    rows = c.fetchall()
    conn.close()
    
    hierarchy = {}
    nodes_by_path = {"": hierarchy}
    
    # Sort by path length to ensure parents are processed before children
    rows.sort(key=lambda x: len(x[0].split('/')))
    
    # First, build all folders
    for row in rows:
        path, name, parent_path, is_folder, config_str = row
        if is_folder:
            config_data = json.loads(config_str) if config_str else {}
            config_data["children"] = {}
            if parent_path == "":
                hierarchy[name] = config_data
            else:
                parent_dict = nodes_by_path.get(parent_path, {})
                if "children" not in parent_dict:
                    parent_dict["children"] = {}
                parent_dict["children"][name] = config_data
            nodes_by_path[path] = config_data
            
    # Then add variables
    for row in rows:
        path, name, parent_path, is_folder, config_str = row
        if not is_folder:
            config_data = json.loads(config_str) if config_str else {}
            if parent_path == "":
                hierarchy[name] = config_data
            else:
                parent_dict = nodes_by_path.get(parent_path, {})
                if "children" not in parent_dict:
                    parent_dict["children"] = {}
                parent_dict["children"][name] = config_data
                
    return hierarchy

def update_node(path, name, parent_path, is_folder, config_data):
    conn = get_connection()
    c = conn.cursor()
    # Strip children from config_data just in case
    clean_config = {k: v for k, v in config_data.items() if k != "children"}
    c.execute('''INSERT OR REPLACE INTO nodes (path, name, parent_path, is_folder, config)
               VALUES (?, ?, ?, ?, ?)''',
            (path, name, parent_path, is_folder, json.dumps(clean_config)))
    conn.commit()
    conn.close()

def delete_node(path):
    conn = get_connection()
    c = conn.cursor()
    # Delete the node and any nested children physically
    c.execute('DELETE FROM nodes WHERE path = ? OR path LIKE ?', (path, path + '/%'))
    conn.commit()
    conn.close()

def get_rules():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT rule_json FROM rules ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]

def save_rules(rules_list):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM rules')
    for rule in rules_list:
        c.execute('INSERT INTO rules (rule_json) VALUES (?)', (json.dumps(rule),))
    conn.commit()
    conn.close()

def get_alarms():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT alarm_json FROM alarms ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]

def save_alarms(alarms_list):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM alarms')
    for alarm in alarms_list:
        c.execute('INSERT INTO alarms (alarm_json) VALUES (?)', (json.dumps(alarm),))
    conn.commit()
    conn.close()
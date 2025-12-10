import os
import json
from pathlib import Path
from datetime import datetime

CONTACTS_DIR = Path(__file__).resolve().parent.parent / "backend" / "contacts"

def normalize_name(folder_name):
    parts = folder_name.split("_")
    timestamp = parts[-1]
    if "2025" not in timestamp:
        return None
    name = "_".join(parts[:-1])
    return name

def load_contact_folder(path):
    msg_path = path / "message.txt"
    state_path = path / "state.json"
    msg = msg_path.read_text().strip() if msg_path.exists() else ""
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    return msg, state

def aggregate_contacts():
    data = {}
    for folder in CONTACTS_DIR.iterdir():
        if not folder.is_dir():
            continue
        name = normalize_name(folder.name)
        if not name:
            continue
        if name not in data:
            data[name] = {
                "folders": [],
                "messages": [],
                "states": [],
                "timestamps": []
            }
        ts_str = folder.name.split("_")[-1]
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H-%M-%S")
        except:
            ts = None
        msg, state = load_contact_folder(folder)
        data[name]["folders"].append(str(folder))
        data[name]["messages"].append(msg)
        data[name]["states"].append(state)
        data[name]["timestamps"].append(ts)
    return data

def compute_clean_output(agg):
    out = {}
    for name, obj in agg.items():
        idx = max(range(len(obj["timestamps"])), key=lambda i: obj["timestamps"][i] or datetime.min)
        latest_state = obj["states"][idx]
        responded = any(len(m.strip()) > 3 for m in obj["messages"])
        out[name] = {
            "num_folders": len(obj["folders"]),
            "responded": responded,
            "latest_state": latest_state,
            "messages": obj["messages"]
        }
    return out

if __name__ == "__main__":
    agg = aggregate_contacts()
    out = compute_clean_output(agg)
    with open("deduped_contacts.json", "w") as f:
        json.dump(out, f, indent=2)
    print("Done. Saved deduped_contacts.json.")

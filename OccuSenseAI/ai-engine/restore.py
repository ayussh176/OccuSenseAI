import os
import json
import shutil
from urllib.parse import unquote

history_dir = r"C:\Users\Ayush Malik\AppData\Roaming\Code\User\History"
workspace_dir = r"d:\promptathon\OccuSenseAI\ai-engine"

restored_count = 0
for d in os.listdir(history_dir):
    entries_file = os.path.join(history_dir, d, "entries.json")
    if not os.path.exists(entries_file):
        continue
        
    try:
        with open(entries_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        resource = data.get("resource", "")
        if not resource.startswith("file:///"):
            continue
            
        filepath = unquote(resource.replace("file:///", "")).replace("/", "\\")
        
        # Check if the file belongs to our workspace and is a python file
        if filepath.lower().startswith(workspace_dir.lower()) and filepath.endswith(".py"):
            # Find the latest entry that has content
            entries = data.get("entries", [])
            if not entries:
                continue
                
            # sort by timestamp descending
            entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            best_entry = None
            best_file = None
            for entry in entries:
                entry_id = entry.get("id")
                entry_file = os.path.join(history_dir, d, entry_id)
                if os.path.exists(entry_file):
                    if os.path.getsize(entry_file) > 0:
                        best_entry = entry
                        best_file = entry_file
                        break
            
            if best_file:
                # Restore the file
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                shutil.copy2(best_file, filepath)
                print(f"Restored: {filepath}")
                restored_count += 1
    except Exception as e:
        print(f"Error processing {d}: {e}")

print(f"Total restored: {restored_count}")

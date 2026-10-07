import json

db_path = '/Users/hungdv-mac/Downloads/ai_assistant_personal/data/builder-data.json'
with open(db_path, 'r') as f:
    db = json.load(f)

if 'sync_urls' not in db:
    db['sync_urls'] = []

with open(db_path, 'w') as f:
    json.dump(db, f, indent=2, ensure_ascii=False)
print("Added sync_urls to db")

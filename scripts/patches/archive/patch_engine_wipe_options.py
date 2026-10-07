import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

wipe_func_old = """export function wipeAllData(): void {
  const store = state();
  store.projects = [];
  store.tasks = [];
  store.notes = [];
  store.sync_urls = [];
  touched();
}"""

wipe_func_new = """export function wipeAllData(options?: { tasks?: boolean, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }): void {
  const store = state();
  if (!options || options.projects) store.projects = [];
  if (!options || options.tasks) store.tasks = [];
  if (!options || options.notes) store.notes = [];
  if (!options || options.sync_urls) store.sync_urls = [];
  
  if (!options || options.chrome_history) {
    const fs = require('fs');
    const path = require('path');
    const outPath = path.join(process.cwd(), "../../data/chrome-history.json");
    if (fs.existsSync(outPath)) {
      fs.unlinkSync(outPath);
    }
  }
  
  touched();
}"""

c = c.replace(wipe_func_old, wipe_func_new)

with open(file_path, "w") as f:
    f.write(c)

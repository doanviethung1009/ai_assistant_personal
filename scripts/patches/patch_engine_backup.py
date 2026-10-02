import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

old_func = """export function wipeAllData(options?: { tasks?: boolean, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }): void {
  const store = state();
  if (!options || options.projects) store.projects = [];"""

new_func = """export function wipeAllData(options?: { tasks?: boolean, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }): void {
  const store = state();

  try {
    const fs = require('fs');
    const path = require('path');
    const backupDir = path.join(process.cwd(), "../../data/backups");
    if (!fs.existsSync(backupDir)) {
      fs.mkdirSync(backupDir, { recursive: true });
    }
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupFile = path.join(backupDir, `builder-data-backup-${timestamp}.json`);
    fs.writeFileSync(backupFile, JSON.stringify(store, null, 2));
    console.log(`[Backup] Data automatically backed up to ${backupFile}`);
  } catch (e) {
    console.error("[Backup] Failed to create backup before wiping:", e);
  }

  if (!options || options.projects) store.projects = [];"""

c = c.replace(old_func, new_func)

with open(file_path, "w") as f:
    f.write(c)

print("Added backup logic to wipeAllData")

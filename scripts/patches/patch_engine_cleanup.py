import sys
import re

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

old_logic = """    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    
    // Backup main database
    const backupFile = path.join(backupDir, `builder-data-backup-${timestamp}.json`);
    fs.writeFileSync(backupFile, JSON.stringify(store, null, 2));
    console.log(`[Backup] Data automatically backed up to ${backupFile}`);

    // Backup chrome history if it exists
    const chromePath = path.join(process.cwd(), "../../data/chrome-history.json");
    if (fs.existsSync(chromePath)) {
      const chromeBackup = path.join(backupDir, `chrome-history-backup-${timestamp}.json`);
      fs.copyFileSync(chromePath, chromeBackup);
      console.log(`[Backup] Chrome history backed up to ${chromeBackup}`);
    }"""

new_logic = """    // Dọn dẹp tất cả các file backup cũ trong thư mục trước
    const files = fs.readdirSync(backupDir);
    for (const file of files) {
      if (file.endsWith('.json')) {
        fs.unlinkSync(path.join(backupDir, file));
      }
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    
    // Backup main database
    const backupFile = path.join(backupDir, `builder-data-backup-${timestamp}.json`);
    fs.writeFileSync(backupFile, JSON.stringify(store, null, 2));
    console.log(`[Backup] Data automatically backed up to ${backupFile}`);

    // Backup chrome history if it exists
    const chromePath = path.join(process.cwd(), "../../data/chrome-history.json");
    if (fs.existsSync(chromePath)) {
      const chromeBackup = path.join(backupDir, `chrome-history-backup-${timestamp}.json`);
      fs.copyFileSync(chromePath, chromeBackup);
      console.log(`[Backup] Chrome history backed up to ${chromeBackup}`);
    }"""

c = c.replace(old_logic, new_logic)

with open(file_path, "w") as f:
    f.write(c)

print("Patched backup logic to keep only the latest backup")

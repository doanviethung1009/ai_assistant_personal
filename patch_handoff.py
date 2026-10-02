import sys
file_path = "docs/AI_HANDOFF_STATE.md"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "- **Chrome History Scraper**: Implemented in `/data`. Uses Node.js `child_process` and macOS `sqlite3` to copy and dump the user's local Google Chrome History database (`~/Library/Application Support/Google/Chrome/Default/History`) into `data/chrome-history.json` for external analysis.",
    "- **Chrome History Scraper**: Implemented in `/data`. Uses Node.js `child_process` and `sqlite3` to dump the Chrome History DB into `data/chrome-history.json`. Supports MacOS, Windows, and Linux dynamically based on OS platform.\n- **Chrome History Viewer**: A dedicated `/history` page that parses `chrome-history.json` and renders the last 1000 visited URLs in a clean table."
)

with open(file_path, "w") as f:
    f.write(c)

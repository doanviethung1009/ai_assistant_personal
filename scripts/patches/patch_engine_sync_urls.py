import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "notes: StoredNote[];\n}",
    "notes: StoredNote[];\n  sync_urls?: string[];\n}"
)
c = c.replace(
    "notes: [],\n  };",
    "notes: [],\n    sync_urls: [],\n  };"
)
c = c.replace(
    "if (data.notes !== undefined) store.notes = data.notes;",
    "if (data.notes !== undefined) store.notes = data.notes;\n  if (data.sync_urls !== undefined) store.sync_urls = data.sync_urls;"
)
c = c.replace(
    "export function listNotes",
    """export function getSyncUrls(): string[] { return state().sync_urls || []; }
export function addSyncUrl(url: string) { const s = state(); if (!s.sync_urls) s.sync_urls = []; if (!s.sync_urls.includes(url)) s.sync_urls.push(url); touched(); }
export function removeSyncUrl(url: string) { const s = state(); if (s.sync_urls) s.sync_urls = s.sync_urls.filter(u => u !== url); touched(); }
export function listNotes"""
)

with open(file_path, "w") as f:
    f.write(c)
print("Patched engine.ts for sync_urls")

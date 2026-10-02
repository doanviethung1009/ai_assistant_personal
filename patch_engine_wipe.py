import sys
file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

wipe_func = """
export function wipeAllData(): void {
  const store = state();
  store.projects = [];
  store.tasks = [];
  store.notes = [];
  store.sync_urls = [];
  touched();
}
"""

c = c + wipe_func

with open(file_path, "w") as f:
    f.write(c)

import sys

file_path = "apps/web/lib/api.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'export async function wipeAllDataApi(): Promise<void> {\n  if (IS_LOCAL) return local(() => engine.wipeAllData());\n}',
    'export async function wipeAllDataApi(options?: { tasks?: boolean, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }): Promise<void> {\n  if (IS_LOCAL) return local(() => engine.wipeAllData(options));\n}'
)

with open(file_path, "w") as f:
    f.write(c)

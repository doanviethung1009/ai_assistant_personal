import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "interface StoreState {",
    "interface StoreState {\n  sync_urls?: string[];"
)
c = c.replace(
    "notes?: StoredNote[];\n  }",
    "notes?: StoredNote[];\n    sync_urls?: string[];\n  }"
)
c = c.replace(
    "s.sync_urls.filter(u => u !== url)",
    "s.sync_urls.filter((u: string) => u !== url)"
)

with open(file_path, "w") as f:
    f.write(c)

print("Patched engine.ts interfaces")

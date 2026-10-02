import sys
file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "  notes?: StoredNote[];\n}): void {",
    "  notes?: StoredNote[];\n  sync_urls?: string[];\n}): void {"
)
with open(file_path, "w") as f:
    f.write(c)

print("Patched replaceAll")

import sys
file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "function state()",
    "export function state()"
)
c = c.replace(
    "function touched()",
    "export function touched()"
)

with open(file_path, "w") as f:
    f.write(c)

print("Exported state and touched")

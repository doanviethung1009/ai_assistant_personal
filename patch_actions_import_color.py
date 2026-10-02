import sys

file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

# I will replace `color: "zinc"` with a randomly picked nice color from a palette.
# Let's write a small helper function at the top.
helper = """
const PALETTE = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16', '#06b6d4', '#d946ef'];
function getRandomColor() {
  return PALETTE[Math.floor(Math.random() * PALETTE.length)];
}
"""

c = c.replace(
    'import { uuid, nowIso } from "@/lib/store/engine";',
    'import { uuid, nowIso } from "@/lib/store/engine";\n' + helper
)

c = c.replace(
    'color: "zinc",',
    'color: getRandomColor(),'
)

with open(file_path, "w") as f:
    f.write(c)

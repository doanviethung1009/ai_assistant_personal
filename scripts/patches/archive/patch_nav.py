import sys
with open("apps/web/lib/nav.ts", "r") as f:
    c = f.read()

c = c.replace(
    "{ href: \"/projects\", label: \"Dự án\" },",
    "{ href: \"/projects\", label: \"Dự án\" },\n  { href: \"/team\", label: \"Team\", short: \"Team\" },"
)

with open("apps/web/lib/nav.ts", "w") as f:
    f.write(c)
print("Patched nav.ts")

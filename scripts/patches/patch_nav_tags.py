import sys
file_path = "apps/web/lib/nav.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    '{ href: "/notes", label: "Sổ tay" },',
    '{ href: "/notes", label: "Sổ tay" },\n  { href: "/tags", label: "Quản lý Tag", short: "Tags" },'
)

with open(file_path, "w") as f:
    f.write(c)

print("Added tags to nav")

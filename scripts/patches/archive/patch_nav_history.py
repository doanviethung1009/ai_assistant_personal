import sys
file_path = "apps/web/lib/nav.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    '{ href: "/tags", label: "Quản lý Tag", short: "Tags" },',
    '{ href: "/tags", label: "Quản lý Tag", short: "Tags" },\n  { href: "/history", label: "Lịch sử duyệt web", short: "Lịch sử" },'
)

with open(file_path, "w") as f:
    f.write(c)

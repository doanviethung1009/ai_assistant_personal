import sys
file_path = "apps/web/lib/nav.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    """  { href: "/", label: "Hôm nay" },
  { href: "/tasks", label: "Tất cả task", short: "Task" },
  { href: "/projects", label: "Dự án" },
  { href: "/team", label: "Team", short: "Team" },
  { href: "/notes", label: "Sổ tay" },
  { href: "/trash", label: "Thùng rác", short: "Rác" },""",
    """  { href: "/", label: "Hôm nay" },
  { href: "/tasks", label: "Tất cả task", short: "Task" },
  { href: "/team", label: "Team", short: "Team" },
  { href: "/projects", label: "Dự án" },
  { href: "/notes", label: "Sổ tay" },
  { href: "/trash", label: "Thùng rác", short: "Rác" },"""
)
with open(file_path, "w") as f:
    f.write(c)

print("Swapped nav order")

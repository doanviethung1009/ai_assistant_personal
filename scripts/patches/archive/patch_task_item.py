import sys
with open("apps/web/components/task-item.tsx", "r") as f:
    c = f.read()

# I want to add an assignee badge next to ProjectBadge
c = c.replace(
    "{task.tags.map((tag) => (",
    "{task.assignee ? (\n              <span className=\"rounded bg-orange-500/15 px-2 py-0.5 text-xs font-medium text-orange-600 dark:text-orange-400\">\n                @{task.assignee}\n              </span>\n            ) : null}\n            {task.tags.map((tag) => ("
)
with open("apps/web/components/task-item.tsx", "w") as f:
    f.write(c)
print("Patched task-item.tsx")

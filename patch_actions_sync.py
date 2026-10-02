import sys

file_path = "apps/web/app/actions.ts"
with open(file_path, "r") as f:
    c = f.read()

# Assignee from ticket
c = c.replace(
    "external_url: `https://onemount.atlassian.net/browse/${key}`\n      });",
    "external_url: `https://onemount.atlassian.net/browse/${key}`,\n        assignee: ticket['Assignee'] ? String(ticket['Assignee']) : null\n      });"
)

with open(file_path, "w") as f:
    f.write(c)
print("Patched actions.ts for assignee sync")

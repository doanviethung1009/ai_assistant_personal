import sys
import re

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "events: [],\n  };",
    "events: [],\n    assignee: (input as any).assignee ?? null,\n  };"
)
c = c.replace(
    "deleted_at: null,\n  };",
    "deleted_at: null,\n    assignee: null,\n  };"
)
c = c.replace(
    "external_url: task.external_url,",
    "external_url: task.external_url,\n    assignee: (task as any).assignee,"
)
with open(file_path, "w") as f:
    f.write(c)


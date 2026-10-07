import sys
file_path = "apps/core/app/api/v1/tasks.py"
with open(file_path, "r") as f:
    c = f.read()
c = c.replace(
    "    include_closed: Annotated[bool, Query",
    "    assignee: Annotated[str | None, Query()] = None,\n    include_closed: Annotated[bool, Query"
)
with open(file_path, "w") as f:
    f.write(c)

file_path = "apps/core/app/services/task_service.py"
with open(file_path, "r") as f:
    c = f.read()
c = c.replace(
    "class TaskFilters(BaseModel):",
    "class TaskFilters(BaseModel):\n    assignee: str | None = None"
)
c = c.replace(
    "        if filters.due_before:\n            stmt = stmt.where(Task.due_at < filters.due_before)",
    "        if filters.due_before:\n            stmt = stmt.where(Task.due_at < filters.due_before)\n        if filters.assignee:\n            stmt = stmt.where(Task.assignee == filters.assignee)"
)
with open(file_path, "w") as f:
    f.write(c)
print("Patched python API")

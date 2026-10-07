import sys
import re

file_path = "apps/web/lib/types.ts"
with open(file_path, "r") as f:
    content = f.read()

# Add assignee to Task interface
old_task = """export interface Task {
  id: string; // uuid
  title: string;
  description: string | null;
  status: TaskStatus;"""

new_task = """export interface Task {
  id: string; // uuid
  title: string;
  description: string | null;
  status: TaskStatus;
  assignee: string | null;"""

if old_task in content:
    content = content.replace(old_task, new_task)
    with open(file_path, "w") as f:
        f.write(content)
    print("Patched types.ts")
else:
    print("Could not find Target in types.ts")

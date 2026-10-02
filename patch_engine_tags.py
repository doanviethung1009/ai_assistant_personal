import sys

file_path = "apps/web/lib/store/engine.ts"
with open(file_path, "r") as f:
    c = f.read()

# Add Tag management functions at the bottom
tag_funcs = """

// ── Tags Management ──────────────────────────────────────────────────────

export interface TagStat {
  name: string;
  taskCount: number;
  noteCount: number;
}

export function getTagsStats(): TagStat[] {
  const store = state();
  const tagMap: Record<string, { t: number; n: number }> = {};
  
  for (const task of aliveTasks()) {
    for (const tag of task.tags) {
      if (!tagMap[tag]) tagMap[tag] = { t: 0, n: 0 };
      tagMap[tag].t++;
    }
  }
  
  for (const note of aliveNotes()) {
    for (const tag of note.tags) {
      if (!tagMap[tag]) tagMap[tag] = { t: 0, n: 0 };
      tagMap[tag].n++;
    }
  }
  
  return Object.entries(tagMap).map(([name, counts]) => ({
    name,
    taskCount: counts.t,
    noteCount: counts.n
  })).sort((a, b) => a.name.localeCompare(b.name));
}

export function renameGlobalTag(oldName: string, newName: string): void {
  const oldT = oldName.trim().toLowerCase();
  const newT = newName.trim().toLowerCase();
  if (!oldT || !newT || oldT === newT) return;
  
  let changed = false;
  
  for (const task of state().tasks) {
    if (task.tags.includes(oldT)) {
      task.tags = [...new Set(task.tags.map(t => t === oldT ? newT : t))];
      task.updated_at = nowIso();
      changed = true;
    }
  }
  
  for (const note of state().notes) {
    if (note.tags.includes(oldT)) {
      note.tags = [...new Set(note.tags.map(t => t === oldT ? newT : t))];
      note.updated_at = nowIso();
      changed = true;
    }
  }
  
  if (changed) touched();
}

export function deleteGlobalTag(name: string): void {
  const target = name.trim().toLowerCase();
  if (!target) return;
  
  let changed = false;
  
  for (const task of state().tasks) {
    if (task.tags.includes(target)) {
      task.tags = task.tags.filter(t => t !== target);
      task.updated_at = nowIso();
      changed = true;
    }
  }
  
  for (const note of state().notes) {
    if (note.tags.includes(target)) {
      note.tags = note.tags.filter(t => t !== target);
      note.updated_at = nowIso();
      changed = true;
    }
  }
  
  if (changed) touched();
}
"""

c = c + tag_funcs

with open(file_path, "w") as f:
    f.write(c)

print("Patched engine.ts with tag functions")

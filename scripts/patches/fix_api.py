import sys

# 1. Update CreateTaskInput in api.ts
with open("apps/web/lib/api.ts", "r") as f:
    api_content = f.read()

api_content = api_content.replace(
    "tags?: string[];\n}",
    "tags?: string[];\n  source?: string;\n  external_id?: string | null;\n  external_url?: string | null;\n}"
)
with open("apps/web/lib/api.ts", "w") as f:
    f.write(api_content)

# 2. Update CreateTaskInput handling in engine.ts
with open("apps/web/lib/store/engine.ts", "r") as f:
    engine_content = f.read()

old_engine = """    is_overdue: false,
    days_until_purge: null,
  });"""
new_engine = """    is_overdue: false,
    days_until_purge: null,
    source: (input as any).source ?? "manual",
    external_id: (input as any).external_id ?? null,
    external_url: (input as any).external_url ?? null,
  });"""
engine_content = engine_content.replace(old_engine, new_engine)

with open("apps/web/lib/store/engine.ts", "w") as f:
    f.write(engine_content)

# 3. Update actions.ts
with open("apps/web/app/actions.ts", "r") as f:
    actions_content = f.read()

actions_content = actions_content.replace(
    "const data = XLSX.utils.sheet_to_json(sheet) as any[];",
    "if (!sheet) throw new Error('No sheet');\n    const data = XLSX.utils.sheet_to_json(sheet) as any[];"
)

actions_content = actions_content.replace(
    "external_url: `https://onemount.atlassian.net/browse/${key}`",
    "source: 'jira',\n        external_id: key,\n        external_url: `https://onemount.atlassian.net/browse/${key}`"
)

with open("apps/web/app/actions.ts", "w") as f:
    f.write(actions_content)

print("Fixed api.ts, engine.ts, actions.ts")

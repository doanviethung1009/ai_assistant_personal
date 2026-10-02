import sys

file_path = "apps/web/app/actions-danger.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'export async function wipeAllDataAction() {\n  await wipeAllDataApi();\n  revalidatePath(\'/\', \'layout\');\n}',
    'export async function wipeAllDataAction(options?: { tasks?: boolean, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }) {\n  await wipeAllDataApi(options);\n  revalidatePath(\'/\', \'layout\');\n}'
)

with open(file_path, "w") as f:
    f.write(c)

import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace('lkFileAction(formData: FormData) {', 'export async function importBulkFileAction(formData: FormData) {')

with open(file_path, "w") as f:
    f.write(c)

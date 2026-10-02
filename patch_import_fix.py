import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'const keyParts = issueKey.split(\'-\');',
    'const keyParts = issueKey ? issueKey.split(\'-\') : [];'
)

with open(file_path, "w") as f:
    f.write(c)


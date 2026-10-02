import sys
file_path = "apps/web/app/actions-import.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'const jiraProjectCode = keyParts.length > 1 ? keyParts[0].toUpperCase() : null;',
    'const jiraProjectCode = keyParts.length > 1 ? keyParts[0]?.toUpperCase() : null;'
)
c = c.replace(
    'const bracketMatches = [...rawSummary.matchAll(/\\[(.*?)\\]/g)].map(m => m[1].trim());',
    'const bracketMatches = [...rawSummary.matchAll(/\\[(.*?)\\]/g)].map(m => m[1]?.trim() || "");'
)
c = c.replace(
    'companyName = validBrackets[0];',
    'companyName = validBrackets[0] || "Others";'
)

with open(file_path, "w") as f:
    f.write(c)


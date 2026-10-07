import sys
with open("apps/web/app/actions.ts", "r") as f:
    c = f.read()
c = c.replace(
    "external_url: `https://onemount.atlassian.net/browse/${key}`",
    "external_id: key,\n        external_url: `https://onemount.atlassian.net/browse/${key}`"
)
with open("apps/web/app/actions.ts", "w") as f:
    f.write(c)

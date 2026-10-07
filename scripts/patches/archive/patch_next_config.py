import sys
file_path = "apps/web/next.config.ts"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'bodySizeLimit: "2mb",',
    'bodySizeLimit: "100mb",'
)

with open(file_path, "w") as f:
    f.write(c)

print("Updated next.config.ts bodySizeLimit to 100mb")

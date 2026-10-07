import sys
file_path = "apps/web/components/url-sync-form.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    "Nhập link đến file Excel (.xlsx) chứa danh sách",
    "Nhập link đến file Excel (.xlsx) hoặc CSV (.csv) chứa danh sách"
)
c = c.replace(
    "placeholder=\"https://example.com/path/to/excel.xlsx\"",
    "placeholder=\"https://example.com/path/to/data.xlsx (hoặc .csv)\""
)
with open(file_path, "w") as f:
    f.write(c)

print("Patched url-sync-form.tsx")

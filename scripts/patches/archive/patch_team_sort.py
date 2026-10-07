import sys
file_path = "apps/web/app/team/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

c = c.replace(
    'const currentSort = sp.sort || "newest";',
    'const currentSort = sp.sort || "all";'
)
c = c.replace(
    """    // 3. Theo thời gian (sort)
    teamTasks.sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return currentSort === "newest" ? dateB - dateA : dateA - dateB;
    });""",
    """    // 3. Theo thời gian (sort)
    if (currentSort !== "all") {
      teamTasks.sort((a, b) => {
        const dateA = new Date(a.created_at).getTime();
        const dateB = new Date(b.created_at).getTime();
        return currentSort === "newest" ? dateB - dateA : dateA - dateB;
      });
    }"""
)
c = c.replace(
    """            {[
              { id: "newest", label: "Mới nhất" },
              { id: "oldest", label: "Cũ nhất" }
            ].map(so => (""",
    """            {[
              { id: "all", label: "Tất cả" },
              { id: "newest", label: "Mới nhất" },
              { id: "oldest", label: "Cũ nhất" }
            ].map(so => ("""
)
c = c.replace(
    "href={makeLink({ sort: so.id === \"newest\" ? undefined : so.id })}",
    "href={makeLink({ sort: so.id === \"all\" ? undefined : so.id })}"
)

with open(file_path, "w") as f:
    f.write(c)
print("Patched team page sort")

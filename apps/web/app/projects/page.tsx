import { ApiErrorPanel } from "@/components/api-error";
import { ProjectForm } from "@/components/project-form";
import { listProjects } from "@/lib/api";
import type { Project } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  let projects: Project[];

  try {
    projects = await listProjects(true);
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Dự án</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Nhóm task theo dự án. Xoá dự án không xoá task, chỉ gỡ liên kết.
        </p>
      </div>

      <ProjectForm />

      {projects.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          Chưa có dự án nào.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {projects.map((project) => (
            <li
              key={project.id}
              className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3"
            >
              <span
                aria-hidden="true"
                className="size-3 shrink-0 rounded-full"
                style={{ backgroundColor: project.color ?? "#4f8cff" }}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  <span className="text-[var(--color-ink-muted)]">
                    {project.key}
                  </span>{" "}
                  {project.name}
                </p>
                {project.description ? (
                  <p className="text-xs text-[var(--color-ink-muted)]">
                    {project.description}
                  </p>
                ) : null}
              </div>
              {project.is_archived ? (
                <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-[var(--color-ink-muted)]">
                  đã lưu trữ
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

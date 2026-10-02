import { ApiErrorPanel } from "@/components/api-error";
import { ProjectForm } from "@/components/project-form";
import { ProjectItem } from "@/components/project-item";
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
            <ProjectItem key={project.id} project={project} />
          ))}
        </ul>
      )}
    </div>
  );
}

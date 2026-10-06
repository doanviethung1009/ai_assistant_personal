import { ApiErrorPanel } from "@/components/api-error";
import { JiraQuickSync } from "@/components/jira-quick-sync";
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
    <div className="flex flex-col gap-8 pb-12 max-w-6xl mx-auto w-full">
      <div className="flex items-start justify-between relative">
        <div className="absolute -inset-1 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg blur opacity-10 pointer-events-none"></div>
        <div className="relative">
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-[var(--color-ink)] to-gray-400 bg-clip-text text-transparent flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 rounded-xl">
              <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-purple-500"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
            </div>
            Dự án & Mục tiêu
          </h1>
          <p className="mt-2 text-sm text-[var(--color-ink-muted)] font-medium">
            Quản lý các dự án lớn, OKRs, hoặc epic. Xoá dự án không xoá task, chỉ gỡ liên kết.
          </p>
        </div>
        <div className="relative z-10">
          <JiraQuickSync />
        </div>
      </div>

      <div className="relative rounded-2xl bg-gradient-to-br from-[var(--color-surface-raised)] to-[var(--color-surface)] p-2 shadow-sm border border-[var(--color-border)]">
        <ProjectForm />
      </div>

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

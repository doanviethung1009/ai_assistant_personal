import { Settings2 } from "lucide-react";

import { ApiErrorPanel } from "@/components/api-error";
import { ChromeHistoryManager } from "@/components/chrome-history-manager";
import { CurrentUserManager } from "@/components/current-user-manager";
import { DataExportGrid } from "@/components/data-export-grid";
import { DataImport } from "@/components/data-import";
import { DataSourceCard } from "@/components/data-source-card";
import { DataTabs, LocalOnlyNotice, parseDataTab } from "@/components/data-tabs";
import { FileUploadManager } from "@/components/file-upload-manager";
import { JiraSyncManager } from "@/components/jira-sync-manager";
import { RestoreJsonManager } from "@/components/restore-json-manager";
import { UrlSyncManager } from "@/components/url-sync-manager";
import { VaultImportManager } from "@/components/vault-import-manager";
import { WipeDataManager } from "@/components/wipe-data-manager";
import {
  IS_LOCAL,
  getAssigneesApi,
  getCurrentUsersApi,
  getSyncUrlsApi,
  listNotes,
  listProjects,
  listTasks,
} from "@/lib/api";

export const dynamic = "force-dynamic";

interface SearchParams {
  tab?: string;
}

const DIVIDER = <div className="h-px w-full bg-[var(--color-border)]/50"></div>;

/**
 * Trang Dữ liệu & Cấu hình, chia bốn tab (`?tab=`): xuất, nhập, đồng bộ, nguy hiểm.
 *
 * Phần nào chỉ chạy ở DATA_SOURCE=file/memory (nhập JSON, khôi phục, Jira, URL đồng
 * bộ, người dùng hiện tại) thì ở chế độ api hiện thông báo thay vì để người dùng bấm
 * rồi mới bị từ chối. Mọi dữ liệu trang cần được tải song song trong một Promise.all.
 */
export default async function DataPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const tab = parseDataTab((await searchParams).tab);

  let taskCount: number;
  let projectCount: number;
  let noteCount: number;
  let projectList: Awaited<ReturnType<typeof listProjects>> = [];
  let syncUrls: string[];
  let currentUsers: string[];
  let assignees: string[];

  try {
    const [tasks, projects, notes, urls, users, assigneeList] = await Promise.all([
      listTasks({ includeClosed: true, limit: 1 }),
      listProjects(true),
      listNotes({ limit: 1 }),
      getSyncUrlsApi(),
      getCurrentUsersApi(),
      getAssigneesApi(),
    ]);
    taskCount = tasks.total;
    projectCount = projects.length;
    projectList = projects.filter((p) => !p.is_archived);
    noteCount = notes.total;
    syncUrls = urls;
    currentUsers = users;
    assignees = assigneeList;
  } catch (error) {
    return (
      <ApiErrorPanel message={error instanceof Error ? error.message : String(error)} />
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 pb-12">
      <div className="relative">
        <div className="absolute -inset-1 rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 opacity-10 blur"></div>
        <div className="relative">
          <h1 className="flex items-center gap-3 bg-gradient-to-r from-[var(--color-ink)] to-gray-400 bg-clip-text text-3xl font-extrabold tracking-tight text-transparent">
            <div className="rounded-xl bg-blue-500/10 p-2">
              <Settings2 className="size-7 text-blue-500" />
            </div>
            Dữ liệu & Cấu hình
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[var(--color-ink-muted)]">
            Quản lý nguồn dữ liệu, xuất/nhập file, đồng bộ Jira và các tuỳ chọn hệ thống nâng cao.
          </p>
        </div>
      </div>

      <DataSourceCard taskCount={taskCount} projectCount={projectCount} noteCount={noteCount} />

      <DataTabs active={tab} />

      {tab === "xuat" && <DataExportGrid />}

      {tab === "nhap" && (
        <div className="flex flex-col gap-8">
          {IS_LOCAL ? (
            <>
              <DataImport allowReplace={IS_LOCAL} />
              {DIVIDER}
              <FileUploadManager />
              {DIVIDER}
              <RestoreJsonManager />
              {DIVIDER}
            </>
          ) : (
            <LocalOnlyNotice feature="Nhập JSON, nhập file và khôi phục từ bản sao lưu" />
          )}
          {/* Chrome và Vault dùng kho riêng, không phụ thuộc DATA_SOURCE nên luôn hiện. */}
          <ChromeHistoryManager />
          {DIVIDER}
          <VaultImportManager />
        </div>
      )}

      {tab === "dong-bo" &&
        (IS_LOCAL ? (
          <div className="flex flex-col gap-8">
            <CurrentUserManager initialUsers={currentUsers} assignees={assignees} />
            <JiraSyncManager
              taskCount={taskCount}
              projects={projectList.map((p) => ({ id: p.id, key: p.key, name: p.name }))}
            />
            <UrlSyncManager initialUrls={syncUrls} />
          </div>
        ) : (
          <LocalOnlyNotice feature="Đồng bộ Jira, URL đồng bộ và cấu hình người dùng hiện tại" />
        ))}

      {tab === "nguy-hiem" && <WipeDataManager assignees={assignees} />}
    </div>
  );
}

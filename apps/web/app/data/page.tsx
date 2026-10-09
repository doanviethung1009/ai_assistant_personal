import { Settings2 } from "lucide-react";

import { ApiErrorPanel } from "@/components/api-error";
import { CurrentUserManager } from "@/components/current-user-manager";
import { CoreImportPanel } from "@/components/core-import-panel";
import { DataExportGrid } from "@/components/data-export-grid";
import { DataImport } from "@/components/data-import";
import { DataSourceCard } from "@/components/data-source-card";
import { DataTabs, LocalOnlyNotice, parseDataTab } from "@/components/data-tabs";
import { FileUploadManager } from "@/components/file-upload-manager";
import { JiraConnectionsManager } from "@/components/jira-connections-manager";
import { JiraSyncManager } from "@/components/jira-sync-manager";
import { RestoreJsonManager } from "@/components/restore-json-manager";
import { TimezonePicker } from "@/components/timezone-picker";
import { UrlSyncManager } from "@/components/url-sync-manager";
import { VaultImportManager } from "@/components/vault-import-manager";
import { WipeDataManager } from "@/components/wipe-data-manager";
import {
  IS_LOCAL,
  getAssigneesApi,
  getCurrentUsersApi,
  getDisplayTimezoneApi,
  getSyncUrlsApi,
  listIntegrations,
  listNotes,
  listProjects,
  listTasks,
  listTimezonesApi,
} from "@/lib/api";
import type { IntegrationConnection, TimezoneOption } from "@/lib/types";

export const dynamic = "force-dynamic";

interface SearchParams {
  tab?: string;
}

const DIVIDER = <div className="h-px w-full bg-[var(--color-border)]/50"></div>;

/**
 * Trang Dữ liệu & Cấu hình, chia bốn tab (`?tab=`): xuất, nhập, đồng bộ, nguy hiểm.
 *
 * Phần nào chỉ chạy ở DATA_SOURCE=file/memory (nhập JSON, khôi phục, xoá hàng loạt)
 * thì ở chế độ api hiện thông báo thay vì để người dùng bấm rồi mới bị từ chối.
 * Từ B4a, Excel, cào URL và kết nối Jira chạy được ở cả hai chế độ (api đi qua
 * upsert-batch và integrations). Mọi dữ liệu trang cần được tải song song trong một Promise.all.
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
  let connections: IntegrationConnection[] = [];
  let connectionsTotal = 0;
  let connectionsError: string | null = null;

  // Múi giờ chỉ cần ở tab đồng bộ. Danh mục lỗi không được làm sập trang: ô nhập vẫn gõ tay được.
  const { timezone, default: tzDefault, source: tzSource } = await getDisplayTimezoneApi();
  let timezoneOptions: TimezoneOption[] = [];
  if (tab === "dong-bo") {
    timezoneOptions = await listTimezonesApi()
      .then((list) => list.items)
      .catch(() => []);
  }

  try {
    const [tasks, projects, notes, urls, users, assigneeList, integrationPage] = await Promise.all([
      listTasks({ includeClosed: true, limit: 1 }),
      listProjects(true),
      listNotes({ limit: 1 }),
      getSyncUrlsApi(),
      getCurrentUsersApi(),
      getAssigneesApi(),
      // Kết nối lỗi (vd. core cũ chưa có /integrations) không được làm sập cả trang.
      IS_LOCAL
        ? Promise.resolve(null)
        : listIntegrations().catch((error: unknown) => {
            connectionsError = error instanceof Error ? error.message : "Không tải được danh sách kết nối";
            return null;
          }),
    ]);
    if (integrationPage) {
      connections = integrationPage.items;
      connectionsTotal = integrationPage.total;
    }
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
            <>
              {/* Chế độ api: JSON đi qua panel có Kiểm tra (dry-run) trước khi ghi đè. */}
              <CoreImportPanel />
              {DIVIDER}
              <DataImport allowReplace={false} kinds={["tasks-csv", "projects-csv", "notes-csv"]} />
              {DIVIDER}
              {/* Excel đi qua upsert-batch của core (B4a) nên cần mật khẩu nhập. */}
              <FileUploadManager requireSecret />
              {DIVIDER}
              <LocalOnlyNotice feature="Khôi phục từ bản sao lưu cục bộ" />
            </>
          )}
          {/* Vault dùng kho riêng, không phụ thuộc DATA_SOURCE nên luôn hiện. */}
          <VaultImportManager />
        </div>
      )}

      {tab === "dong-bo" && (
        // Người dùng hiện tại, URL đồng bộ, cào URL (upsert-batch) và kết nối Jira đều dùng
        // được ở cả hai chế độ. Sync Jira từ kết nối đã lưu ở chế độ api nằm ở nút Cào ngay (B4b).
        <div className="flex flex-col gap-8">
          <CurrentUserManager initialUsers={currentUsers} assignees={assignees} />
          <TimezonePicker
            current={{ timezone, default: tzDefault, source: tzSource }}
            options={timezoneOptions}
          />
          {IS_LOCAL ? (
            <JiraSyncManager
              taskCount={taskCount}
              projects={projectList.map((p) => ({ id: p.id, key: p.key, name: p.name }))}
            />
          ) : (
            <>
              {connectionsError !== null && (
                <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-400">
                  Không tải được danh sách kết nối Jira: {connectionsError}
                </p>
              )}
              {connectionsTotal > connections.length && (
                <p role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-[var(--color-ink-muted)]">
                  Chỉ hiện {connections.length}/{connectionsTotal} kết nối (giới hạn 100 của core); phần còn lại chưa hiển thị.
                </p>
              )}
              <JiraConnectionsManager connections={connections} />
            </>
          )}
          <UrlSyncManager initialUrls={syncUrls} requireSecret={!IS_LOCAL} />
        </div>
      )}

      {tab === "nguy-hiem" &&
        (IS_LOCAL ? (
          <WipeDataManager assignees={assignees} />
        ) : (
          // Chế độ api chưa có endpoint xoá hàng loạt. Trước đây nút vẫn hiện và báo
          // "thành công" dù không xoá gì.
          <LocalOnlyNotice feature="Xoá dữ liệu hàng loạt" />
        ))}
    </div>
  );
}

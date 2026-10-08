"use client";

import { useState, useTransition } from "react";
import { wipeAllDataAction } from "@/app/actions-danger";
import { useRouter } from "next/navigation";

export function WipeDataManager({ assignees = [] }: { assignees?: string[] }) {
  const [confirmText, setConfirmText] = useState("");
  const [wipeTarget, setWipeTarget] = useState<string>("tasks");
  const [assignee, setAssignee] = useState("");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const handleWipe = () => {
    if (wipeTarget === "tasks_assignee" && !assignee.trim()) {
      alert("Vui lòng nhập tên người cần xoá task!");
      return;
    }
    if (confirmText !== "DELETE") {
      alert("Vui lòng gõ chữ DELETE (viết hoa) để xác nhận!");
      return;
    }
    
    const msg = wipeTarget === "all" 
      ? "BẠN CÓ CHẮC CHẮN KHÔNG? Toàn bộ Task, Dự án, Sổ tay sẽ bị xoá vĩnh viễn!"
      : "Bạn có chắc muốn xoá dữ liệu đã chọn? Hành động này không thể hoàn tác!";
      
    if (!confirm(msg)) return;

    startTransition(async () => {
      let options = undefined;

      if (wipeTarget !== "all") {
        // Mỗi lựa chọn bật đúng MỘT cờ; ô nhập tên chỉ dùng cho tasks_assignee.
        options = {
          tasks: wipeTarget === "tasks",
          tasks_work: wipeTarget === "tasks_work",
          tasks_personal: wipeTarget === "tasks_personal",
          tasks_team: wipeTarget === "tasks_team",
          tasks_assignee: wipeTarget === "tasks_assignee" ? assignee.trim() : undefined,
          projects: wipeTarget === "projects",
          notes: wipeTarget === "notes",
          vault: wipeTarget === "vault",
          sync_urls: wipeTarget === "sync_urls",
          chrome_history: wipeTarget === "chrome_history"
        };
      }

      try {
        await wipeAllDataAction(options);
      } catch {
        alert("Xoá dữ liệu thất bại. Kiểm tra DATA_SOURCE và log của web.");
        return;
      }
      setConfirmText("");
      alert("Đã xoá dữ liệu thành công!");
      router.push("/");
    });
  };

  return (
    <section className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 mt-6">
      <h2 className="text-sm font-semibold text-red-600 dark:text-red-400">Vùng Nguy Hiểm (Danger Zone)</h2>
      <p className="mt-1 text-xs text-red-600/80 dark:text-red-400/80 mb-3">
        Xoá dữ liệu hiện tại trong hệ thống. Hành động này <b>KHÔNG THỂ</b> hoàn tác!
      </p>
      
      <div className="mb-4">
        <label className="block text-xs font-medium text-red-700/80 mb-1">Chọn dữ liệu cần xoá:</label>
        <select 
          value={wipeTarget} 
          onChange={(e) => setWipeTarget(e.target.value)}
          disabled={pending}
          className="rounded-md border border-red-500/30 bg-[var(--color-surface)] px-3 py-1.5 text-sm outline-none focus:border-red-500"
        >
          <option value="tasks">Xoá TẤT CẢ Task (cả Công việc &amp; Cá nhân)</option>
          <option value="tasks_work">Chỉ xoá task CÔNG VIỆC (Jira), giữ task cá nhân</option>
          <option value="tasks_team">Chỉ xoá task công việc của NGƯỜI KHÁC (giữ việc của tôi)</option>
          <option value="tasks_personal">Chỉ xoá task CÁ NHÂN</option>
          <option value="tasks_assignee">Xoá task công việc theo 1 NGƯỜI cụ thể (nhập tên)</option>
          <option value="projects">Chỉ xoá Dự án (Projects)</option>
          <option value="notes">Chỉ xoá Sổ tay (Notes)</option>
          <option value="vault">Chỉ xoá Két bảo mật (Vault)</option>
          <option value="sync_urls">Chỉ xoá Danh sách URL Cào dữ liệu</option>
          <option value="chrome_history">Chỉ xoá Lịch sử Chrome History</option>
          <option value="all">⚠️ Xoá TOÀN BỘ dữ liệu (Tất cả, nguy hiểm)</option>
        </select>
        {wipeTarget === "tasks_assignee" && (
          <div className="relative mt-2">
            <input
              type="text"
              list="assignees-list"
              placeholder="Tên người (nhiều người cách nhau dấu phẩy)"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              disabled={pending}
              className="block w-full rounded-md border border-red-500/30 bg-[var(--color-surface)] px-3 py-1.5 text-sm outline-none focus:border-red-500"
            />
            <datalist id="assignees-list">
              {assignees.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="Gõ DELETE để xác nhận"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          disabled={pending}
          className="flex-1 rounded-md border border-red-500/30 bg-[var(--color-surface)] px-3 py-1.5 text-sm outline-none focus:border-red-500 disabled:opacity-50"
        />
        <button
          onClick={handleWipe}
          disabled={pending || confirmText !== "DELETE"}
          className="rounded-md bg-red-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {pending ? "Đang xử lý..." : "Xoá Dữ Liệu"}
        </button>
      </div>
    </section>
  );
}

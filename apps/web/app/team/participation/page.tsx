import { ApiErrorPanel } from "@/components/api-error";
import { TeamParticipation } from "@/components/team-participation";
import { TeamTabs } from "@/components/team-tabs";
import { getDisplayTimezoneApi, getParticipation } from "@/lib/api";
import { todayInDisplayTz } from "@/lib/format";
import { resolvePeriod } from "@/lib/period";

export const dynamic = "force-dynamic";

/** Khớp giới hạn của API: tối đa 50 người, mỗi tên 1-200 ký tự. */
const MAX_PEOPLE = 50;
const MAX_NAME_LEN = 200;

/**
 * Tab "Tham dự dự án" của khu Team: mỗi người gánh bao nhiêu % task của từng project.
 *
 * Tách khỏi /team để lọc danh sách không phải gọi lại API này, và ngược lại chọn người ở
 * đây không phải tải lại hàng nghìn task của danh sách. Lựa chọn nằm trên URL
 * (?people=A&people=B).
 */
export default async function TeamParticipationPage({
  searchParams,
}: {
  searchParams: Promise<{ people?: string | string[]; range?: string; from?: string; to?: string }>;
}) {
  const sp = await searchParams;
  // Lọc ở đây để URL dài hoặc có tên rỗng không biến thành lỗi 422 từ API.
  const people = [
    ...new Set(
      [sp.people ?? []]
        .flat()
        .map((n) => n.trim())
        .filter((n) => n.length > 0 && n.length <= MAX_NAME_LEN),
    ),
  ].slice(0, MAX_PEOPLE);

  // "Hôm nay" theo múi giờ người dùng đã chọn, cùng múi giờ backend dùng để đổi ngày sang UTC.
  const { timezone } = await getDisplayTimezoneApi();
  const period = resolvePeriod(sp.range, sp.from, sp.to, todayInDisplayTz(timezone));

  let data;
  try {
    data = await getParticipation(people, { from: period.from, to: period.to });
  } catch (error) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 pb-12">
        <TeamTabs active="participation" />
        <ApiErrorPanel message={error instanceof Error ? error.message : String(error)} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 pb-12">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">Giao việc / Team</h1>
        <p className="mt-2 text-sm font-medium text-[var(--color-ink-muted)]">
          Tổng hợp task công việc (Jira) của cả team. Task cá nhân không hiện ở đây.
        </p>
      </div>
      <TeamTabs active="participation" />
      <TeamParticipation data={data} selectedParam={people} period={period} />
    </div>
  );
}

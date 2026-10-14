import "server-only";

/**
 * Cache GET ngắn hạn trong process cho mọi lời gọi core API (xem coreFetch trong api.ts).
 *
 * Vì sao có: web dùng CHUNG một API key nên mọi trang và mọi người dùng chung một bucket rate
 * limit. Click filter chỉ đổi searchParams nhưng Next render lại cả page, gọi lại timezone,
 * projects, stats, current-users... Dữ liệu đó không đổi giữa hai click, nên dùng lại vài giây
 * và gộp các lần gọi đồng thời vào một promise.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  CACHE NÀY DÙNG CHUNG CHO MỌI NGƯỜI DÙNG, KHOÁ CHỈ LÀ PATH.
 *
 *  Chỉ an toàn khi web gọi core bằng MỘT API key dùng chung (hiện tại). Khi web gửi
 *  `Authorization: Bearer` theo từng người (spec auth-multiuser), core trả dữ liệu và quyền
 *  (can_edit...) khác nhau theo người, và cache theo path sẽ đưa dữ liệu của A cho B.
 *  coreFetch vì vậy BỎ QUA cache khi request có header Authorization. Muốn cache lại thì phải
 *  đưa user id vào khoá, đừng gỡ rào đó.
 *
 *  Giá trị trả về dùng chung theo tham chiếu: KHÔNG sửa tại chỗ (sort, push...), hãy sao chép.
 * ══════════════════════════════════════════════════════════════════════
 *
 * State nằm trên globalThis vì Next tách module graph giữa Server Component và Server Action
 * (xem .agents/rules/web-conventions.md); nếu để biến module thì invalidate trong action chỉ xoá
 * bản của action, còn trang vẫn đọc bản cũ. Mọi mutation (coreFetch không phải GET) và
 * revalidateAll() gọi invalidateCoreCache(). TTL ngắn lo phần thay đổi từ ngoài (Jira sync nền,
 * client khác). Lỗi không được giữ lại. Giới hạn số mục để không phình RAM.
 */
const TTL_MS = 10_000;
const MAX_ENTRIES = 200;

interface Entry {
  at: number;
  version: number;
  promise: Promise<unknown>;
}

interface CacheState {
  version: number;
  entries: Map<string, Entry>;
}

const g = globalThis as typeof globalThis & { __coreCache?: CacheState };
const state: CacheState = (g.__coreCache ??= { version: 0, entries: new Map() });

export function invalidateCoreCache(): void {
  state.version += 1;
  state.entries.clear();
}

export function cachedGet<T>(
  key: string,
  loader: () => Promise<T>,
  ttlMs: number = TTL_MS,
): Promise<T> {
  const { entries } = state;
  const now = Date.now();
  const hit = entries.get(key);
  if (hit && hit.version === state.version && now - hit.at < ttlMs) {
    return hit.promise as Promise<T>;
  }
  const promise = loader();
  const fresh: Entry = { at: now, version: state.version, promise };
  if (entries.size >= MAX_ENTRIES) {
    const oldest = entries.keys().next().value;
    if (oldest !== undefined) entries.delete(oldest);
  }
  entries.set(key, fresh);
  promise.catch(() => {
    if (entries.get(key) === fresh) entries.delete(key);
  });
  return promise;
}

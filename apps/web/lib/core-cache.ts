import "server-only";

/**
 * Cache GET ngắn hạn trong process cho mọi lời gọi core API (xem coreFetch trong api.ts).
 *
 * Vì sao có: rate limit của core tính theo từng người dùng (JWT), nhưng mỗi click filter chỉ đổi
 * searchParams mà Next vẫn render lại cả page và gọi lại projects, stats, agenda... Dữ liệu đó không
 * đổi giữa hai click, nên dùng lại vài giây (đỡ request và độ trễ) và gộp các lần gọi đồng thời vào
 * một promise.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  CACHE NÀY DÙNG CHUNG CHO MỌI NGƯỜI DÙNG: KHOÁ PHẢI CÓ uid:sv.
 *
 *  Core trả dữ liệu và quyền (can_edit...) khác nhau theo người, nên khoá chỉ theo path sẽ đưa
 *  dữ liệu của A cho B. Khoá = `${uid}:${sv}\u0000${path}` (cacheKey), `sv` trong khoá để thu hồi
 *  phiên ra khoá mới. `identity` rỗng là lỗi lập trình và ném ngay; đừng gỡ rào này, đừng thêm
 *  đường gọi cachedGet bỏ qua identity. Mọi lời gọi ghi xoá TOÀN BỘ cache (mọi người dùng).
 *  Test khoá hành vi: tests/core-cache.test.ts, tests/core-fetch.test.ts (T1-T8).
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

/** Chỉ cho test: số mục đang giữ. */
export function coreCacheSize(): number {
  return state.entries.size;
}

export function invalidateCoreCache(): void {
  state.version += 1;
  state.entries.clear();
}

/** Khoá cache: danh tính người dùng + path. Hàm thuần để test được. */
export function cacheKey(identity: string, path: string): string {
  if (!identity) throw new Error("core-cache: thiếu identity (uid:sv), cấm cache không theo người dùng");
  return `${identity}\u0000${path}`;
}

export function cachedGet<T>(identity: string, path: string, loader: () => Promise<T>): Promise<T> {
  const key = cacheKey(identity, path);
  const { entries } = state;
  const now = Date.now();
  const hit = entries.get(key);
  if (hit && hit.version === state.version && now - hit.at < TTL_MS) {
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

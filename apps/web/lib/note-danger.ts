/**
 * Nhận diện nội dung đáng cảnh báo trong một note.
 *
 * Hai nhóm khác nhau, đừng gộp:
 *
 *   detectDanger()      lệnh có thể phá dữ liệu nếu chạy. Dùng để gợi ý tích
 *                       sẵn `is_dangerous` ở form, và để hiện cảnh báo trước
 *                       khi copy.
 *
 *   detectSecretHint()  dấu hiệu note đang chứa mật khẩu hoặc khoá. Note lưu
 *                       ở dạng văn bản thuần trong Postgres hoặc file JSON,
 *                       KHÔNG mã hoá, nên đây là thứ cần nhắc ngay lúc nhập.
 *
 * Đây là heuristic, không phải bộ phân tích cú pháp. Nó sẽ bỏ sót, và đôi khi
 * báo sai. Vì vậy `is_dangerous` trong database là cờ do người dùng quyết
 * định, còn hàm này chỉ đề xuất. Không bao giờ dùng kết quả ở đây để chặn
 * người dùng lưu note.
 *
 * File này KHÔNG "server-only": form ở client cũng cần gọi để tích sẵn ô
 * đánh dấu ngay khi người dùng đang gõ.
 */

export interface Signal {
  /** Mô tả ngắn để hiện cho người dùng. */
  reason: string;
}

interface Rule {
  test: RegExp;
  reason: string;
}

const DANGER_RULES: Rule[] = [
  {
    test: /\brm\s+(-[a-z]*[rf][a-z]*\s+)+/i,
    reason: "rm với cờ -r hoặc -f: xoá thư mục không hỏi lại",
  },
  {
    test: /\bdrop\s+(table|database|schema|role|user)\b/i,
    reason: "DROP: xoá hẳn đối tượng trong database",
  },
  {
    test: /\btruncate\s+(table\s+)?\w+/i,
    reason: "TRUNCATE: xoá toàn bộ dòng, không ghi WAL từng dòng nên khó phục hồi",
  },
  {
    test: /\bdelete\s+from\b(?![\s\S]*\bwhere\b)/i,
    reason: "DELETE FROM không có WHERE: xoá mọi dòng trong bảng",
  },
  {
    test: /\bupdate\s+[\w."]+\s+set\b(?![\s\S]*\bwhere\b)/i,
    reason: "UPDATE không có WHERE: ghi đè mọi dòng trong bảng",
  },
  {
    test: /\bdocker\s+(compose\s+)?down\b[\s\S]*(-v|--volumes)\b/i,
    reason: "docker compose down -v: xoá named volume, mất dữ liệu Postgres",
  },
  {
    test: /\bdocker\s+(volume\s+rm|system\s+prune|volume\s+prune)\b/i,
    reason: "Dọn volume hoặc prune: xoá dữ liệu của container đã dừng",
  },
  {
    test: /\bkubectl\s+delete\b/i,
    reason: "kubectl delete: xoá tài nguyên trong cluster",
  },
  {
    test: /\b(mkfs(\.\w+)?|dd\s+if=)/i,
    reason: "Ghi trực tiếp lên thiết bị: xoá sạch ổ đĩa",
  },
  {
    test: />\s*\/dev\/(sd|nvme|hd)\w*/i,
    reason: "Ghi thẳng vào block device",
  },
  {
    test: /\bgit\s+(push\s+[\s\S]*(--force|-f)\b|reset\s+--hard\b|clean\s+-[a-z]*f)/i,
    reason: "Git phá lịch sử hoặc xoá file chưa commit",
  },
  {
    test: /\bchmod\s+(-R\s+)?777\b/i,
    reason: "chmod 777: mở quyền ghi cho mọi user",
  },
  {
    test: /\b(shutdown|reboot|halt|poweroff)\b/i,
    reason: "Tắt hoặc khởi động lại máy",
  },
  {
    test: /\balter\s+(table|database)\b[\s\S]*\bdrop\s+column\b/i,
    reason: "DROP COLUMN: mất dữ liệu của cột đó",
  },
  {
    test: /\bmake\s+reset\b/i,
    reason: "make reset: xoá toàn bộ volume rồi dựng lại",
  },
];

/**
 * Bắt gán giá trị cho biến trông giống bí mật, ví dụ:
 *   PASSWORD=abc123        password: "abc123"
 *   API_KEY=sk-xxxx        --token abcdef
 * Chỉ báo khi giá trị dài từ 6 ký tự, để bỏ qua placeholder như
 * PASSWORD=CHANGE_ME thì vẫn báo (đúng, vì đó là chỗ sẽ điền khoá thật).
 */
const SECRET_RULES: Rule[] = [
  {
    test: /\b(password|passwd|pwd|secret|api[_-]?key|token|access[_-]?key|private[_-]?key)\b\s*[:=]\s*\S{6,}/i,
    reason: "Trông như có gán mật khẩu hoặc khoá",
  },
  {
    test: /\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp):\/\/[^\s:]+:[^\s@]+@/i,
    reason: "Connection string có nhúng mật khẩu",
  },
  {
    test: /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    reason: "Nội dung private key",
  },
  {
    test: /\b(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})/,
    reason: "Trông như API key thật của một dịch vụ",
  },
  {
    test: /\bAKIA[0-9A-Z]{16}\b/,
    reason: "Trông như AWS access key id",
  },
];

function run(rules: Rule[], text: string): Signal[] {
  if (!text) return [];
  const found: Signal[] = [];
  for (const rule of rules) {
    if (rule.test.test(text)) {
      found.push({ reason: rule.reason });
    }
  }
  return found;
}

/** Lệnh có thể gây mất dữ liệu nếu đem chạy. */
export function detectDanger(content: string): Signal[] {
  return run(DANGER_RULES, content);
}

export function looksDangerous(content: string): boolean {
  return detectDanger(content).length > 0;
}

/** Dấu hiệu note đang chứa mật khẩu hoặc khoá. */
export function detectSecretHint(content: string): Signal[] {
  return run(SECRET_RULES, content);
}

export function looksLikeSecret(content: string): boolean {
  return detectSecretHint(content).length > 0;
}

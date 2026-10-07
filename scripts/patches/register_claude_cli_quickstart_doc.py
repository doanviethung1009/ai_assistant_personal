"""Đăng ký docs/CLAUDE_CLI_QUICKSTART.md vào apps/web/lib/docs.ts (idempotent).

Chạy lại nhiều lần an toàn: nếu slug đã có thì không làm gì. Đặt tên không bắt
đầu bằng patch_/fix_ vì hook .claude/hooks/no-patch-scripts.sh chặn các tên đó.
"""
from pathlib import Path

DOCS_TS = Path(__file__).resolve().parents[2] / "apps/web/lib/docs.ts"
SLUG = "claude-cli-quickstart"
ANCHOR = '  {\n    slug: "codex-operating-guide",'
ENTRY = '''  {
    slug: "claude-cli-quickstart",
    title: "Claude CLI Quickstart (multi-agent)",
    description: "Chạy Claude Code với cấu hình multi-agent của repo: subagent, hook an toàn, quyền và quy trình commit/push.",
    category: "Quy ước Code (AI Rules)",
    file: path.join("docs", "CLAUDE_CLI_QUICKSTART.md"),
  },
'''

src = DOCS_TS.read_text(encoding="utf-8")
if f'slug: "{SLUG}"' in src:
    print("Đã đăng ký, bỏ qua")
elif ANCHOR not in src:
    raise SystemExit("Không tìm thấy điểm neo trong docs.ts")
else:
    DOCS_TS.write_text(src.replace(ANCHOR, ENTRY + ANCHOR, 1), encoding="utf-8")
    print("Đã đăng ký CLAUDE_CLI_QUICKSTART vào docs.ts")

#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  PreToolUse hook cho Write: chặn việc tạo script patch_*.py / fix_*.py.
#
#  Lịch sử repo có ~70 file (nay đã chuyển vào scripts/patches/archive/: patch_actions_import_final,
#  final2, final3, final4...) - dấu hiệu agent sửa code gián tiếp bằng
#  script Python thay vì Edit trực tiếp, rồi thử lại nhiều vòng. Cách đó
#  khó review và để lại rác. Claude Code có Edit/Write nên không cần.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

path="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')"

case "$(basename "$path")" in
  patch_*.py|fix_*.py|patch_*.js|fix_*.js)
    echo "BLOCKED: đừng tạo script patch để sửa code. Dùng Edit trực tiếp trên file đích." >&2
    exit 2 ;;
esac
exit 0

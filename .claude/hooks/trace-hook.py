#!/usr/bin/env python3
"""Hook ghi vết phiên Claude Code (Stop / SubagentStop / SessionEnd).

Vì sao có: nhật ký AI viết tay (đã gỡ) là lời tự khai của model nên
có thể sai hoặc thiếu, và quá ngắn để dùng làm dữ liệu train. Hook do harness
chạy, không phụ thuộc model "nhớ" ghi.

Ghi gì, ở đâu (mặc định ~/.claude/trace/ai_assistant_personal/, ghi đè bằng
CLAUDE_TRACE_DIR):
  turns.jsonl            Stop/SubagentStop: MỘT dòng JSON mỗi lượt.
  sessions/<sid>.<t>.jsonl   SessionEnd: bản sao transcript ĐÃ LỌC SECRET.
  sessions/<sid>/subagent-<agent_id>.jsonl   SubagentStop: transcript subagent đã lọc.
  errors.log             lỗi của chính hook (chỉ loại lỗi, không có nội dung).

══════════════════════════════════════════════════════════════════════
  MẶC ĐỊNH TẮT: chỉ chạy khi CLAUDE_TRACE_ENABLED=1.
  HOOK NÀY KHÔNG ĐƯỢC LÀM HỎNG PHIÊN LÀM VIỆC.
  Luôn exit 0, không in gì ra stdout, không gọi mạng, không chặn tool,
  không ghi vào repo, có báo thức tự ngắt. Mọi dữ liệu qua trace_redact
  TRƯỚC khi chạm đĩa. Xem docs/CLAUDE_TRACE_HOOKS.md.
══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import fcntl
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_redact as R  # noqa: E402

DEFAULT_DIR = Path.home() / ".claude" / "trace" / "ai_assistant_personal"
# Báo thức tự ngắt: hook treo thì thoát êm thay vì để harness giết giữa chừng.
# Phải nhỏ hơn `timeout` khai trong settings.json (Stop 10s, SessionEnd 30s).
ALARM_SECONDS = {"SessionEnd": 25}
ALARM_DEFAULT = 8

MAX_PROMPT = 20_000
MAX_ASSISTANT = 4_000
MAX_DIFFSTAT = 2_000
TAIL_BYTES = 16 * 1024 * 1024  # đoạn cuối transcript để tìm prompt của User
OMIT_ABOVE = 20_000  # chuỗi dài không có khoảng trắng = blob base64 (ảnh), bỏ đi


class _Timeout(Exception):
    pass


def _on_alarm(_sig: int, _frm: Any) -> None:
    raise _Timeout()


# ═════════════════════════════════════════════════════════════════════════
#  Thư mục đích
# ═════════════════════════════════════════════════════════════════════════


def trace_dir(project_dir: str | None) -> Path:
    """Thư mục trace, đảm bảo NẰM NGOÀI repo.

    Đường dẫn trong repo dễ bị `git add .` nhặt lên và push dữ liệu chứa
    secret/Jira công ty. Từ chối thẳng thay vì tin vào .gitignore.
    """
    d = Path(os.environ.get("CLAUDE_TRACE_DIR") or DEFAULT_DIR).expanduser().resolve()
    if project_dir:
        proj = Path(project_dir).resolve()
        if d == proj or proj in d.parents:
            raise RuntimeError("trace dir nằm trong repo")
    return d


def _mkdir_private(path: Path) -> None:
    """Tạo thư mục quyền 700 (chmod tường minh vì umask làm lệch mode của makedirs)."""
    missing = []
    p = path
    while not p.exists():
        missing.append(p)
        p = p.parent
    for m in reversed(missing):
        m.mkdir(mode=0o700)
        os.chmod(m, 0o700)


def _append_line(path: Path, line: str) -> None:
    """Nối đúng một dòng. O_APPEND + flock; không bao giờ cắt hay ghi đè file."""
    # O_NOFOLLOW: không nối vào file đích của một symlink do người khác cài sẵn.
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.fchmod(fd, 0o600)  # file có sẵn với quyền lỏng thì siết lại
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)  # đóng fd cũng nhả khoá


def prune_old(base: Path) -> None:
    """Xoá transcript trong sessions/ cũ hơn CLAUDE_TRACE_RETENTION_DAYS (mặc định 90, 0 = giữ mãi).

    Transcript mới là phần phình to (MB mỗi phiên) và chứa dữ liệu nhạy cảm nhất, nên
    không để tồn tại vô hạn. `turns.jsonl` (chỉ mục nhỏ) không bị đụng. Chỉ xoá file
    thường nằm DƯỚI base/sessions (lstat: không theo symlink), tên .jsonl hoặc .tmp-*.
    """
    try:
        days = int(os.environ.get("CLAUDE_TRACE_RETENTION_DAYS", "90"))
    except ValueError:
        days = 90
    root = base / "sessions"
    if days <= 0 or not root.is_dir() or root.is_symlink():
        return
    cutoff = time.time() - days * 86400
    for path in root.rglob("*"):
        try:
            st = path.lstat()
            if (stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff
                    and (path.suffix == ".jsonl" or path.name.startswith(".tmp-"))):
                path.unlink()
        except OSError:
            continue
    for d in sorted((p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()), reverse=True):
        try:
            d.rmdir()  # chỉ thành công khi đã rỗng
        except OSError:
            pass


def log_error(base: Path | None, where: str, exc: BaseException) -> None:
    """Ghi loại lỗi, KHÔNG ghi thông điệp: thông điệp exception có thể chứa dữ liệu."""
    msg = f"{datetime.now(timezone.utc).isoformat()} {where} {type(exc).__name__}"
    print(f"trace-hook: {where} {type(exc).__name__}", file=sys.stderr)
    if base is None:
        return
    try:
        _mkdir_private(base)
        _append_line(base / "errors.log", msg)
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════
#  Thu thập dữ liệu
# ═════════════════════════════════════════════════════════════════════════


def _git(cwd: str, *args: str) -> str:
    """Chạy git chỉ-đọc, cục bộ, timeout ngắn. Lỗi thì trả chuỗi rỗng."""
    try:
        out = subprocess.run(
            # Vô hiệu hoá lệnh do config repo đích quy định (core.fsmonitor, diff.external):
            # repo bên thứ ba không được chạy code mỗi lượt Stop.
            ["git", "-c", "core.fsmonitor=false", "-C", cwd, *args],
            capture_output=True, text=True, timeout=3, stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},  # đừng tranh khoá index của phiên
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _text_of(content: Any) -> str | None:
    """Prompt thật của User, hoặc None nếu dòng này là tool_result/không phải văn bản."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p) or None
    return None


def _is_system_text(text: str) -> bool:
    """Thông báo do harness chèn (task-notification, ci-monitor-event) chứ không phải User gõ."""
    t = text.lstrip()
    return t.startswith(("<task-notification", "<ci-monitor-event", "[SYSTEM NOTIFICATION"))


def last_user_prompt(transcript_path: str, prompt_id: str | None = None) -> str | None:
    """Prompt User gần nhất trong transcript.

    Định dạng transcript KHÔNG được tài liệu Claude Code mô tả; quy tắc dưới
    đây suy ra từ file thật: dòng type=user, không isMeta/isSidechain, content
    là chuỗi hoặc mảng không có tool_result. Ưu tiên dòng có promptId khớp
    `prompt_id` của hook và origin.kind=human. Thông báo tác vụ nền cũng là
    type=user nên phải loại, nếu không `prompt` của lượt sau tác vụ nền sẽ là
    thông báo hệ thống. Đổi định dạng thì hàm trả None, hook vẫn chạy.
    """
    with open(transcript_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read()
    lines = data.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]  # dòng đầu của đoạn cắt có thể dở
    fallback: str | None = None
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
            continue
        origin = (d.get("origin") or {}).get("kind")
        if origin is not None and origin != "human":
            continue
        text = _text_of((d.get("message") or {}).get("content"))
        if not text or not text.strip() or _is_system_text(text):
            continue
        if prompt_id and d.get("promptId") == prompt_id:
            return text
        if fallback is None:
            fallback = text
            if not prompt_id:
                return fallback
    return fallback


def first_user_text(transcript_path: str) -> str | None:
    """Đề bài giao cho subagent: dòng user đầu tiên trong transcript của nó."""
    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f):
            if i > 200:
                break
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if d.get("type") == "user":
                text = _text_of((d.get("message") or {}).get("content"))
                if text and text.strip():
                    return text
    return None


def _clip(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    return s if len(s) <= n else s[:n] + f"…[cắt, gốc {len(s)} ký tự]"


def build_turn(ev: dict[str, Any], hook: str) -> dict[str, Any]:
    cwd = ev.get("cwd") or os.getcwd()
    prompt = None
    tp = ev.get("transcript_path")
    if tp:
        try:
            prompt = last_user_prompt(tp, ev.get("prompt_id"))
        except Exception:
            prompt = None  # thiếu/hỏng transcript không được làm mất dòng tóm tắt
    stat = _git(cwd, "diff", "--stat", "--no-ext-diff", "--no-textconv")
    rec: dict[str, Any] = {
        "v": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": ev.get("session_id"),
        "hook": hook,
        "cwd": cwd,
        "git_branch": _git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or None,
        "diff_stat": "\n".join(stat.splitlines()[-15:]) if stat else "",
        "prompt_id": ev.get("prompt_id"),
        "prompt": prompt,
        # Lời model tự khai về lượt này: để ĐỐI CHIẾU với diff_stat thật.
        "last_assistant_message": ev.get("last_assistant_message"),
        "transcript_path": tp,
    }
    if hook == "SubagentStop":
        rec["agent_id"] = ev.get("agent_id")
        rec["agent_type"] = ev.get("agent_type")
        rec["agent_transcript_path"] = ev.get("agent_transcript_path")
        # `prompt` ở trên là prompt của User gửi orchestrator; đề bài của chính subagent nằm ở đây.
        atp = ev.get("agent_transcript_path")
        try:
            rec["agent_prompt"] = first_user_text(atp) if atp else None
        except Exception:
            rec["agent_prompt"] = None
    return rec


# ═════════════════════════════════════════════════════════════════════════
#  Sao chép transcript đã lọc
# ═════════════════════════════════════════════════════════════════════════


def _drop_blobs(obj: Any) -> Any:
    """Bỏ blob nhị phân (ảnh base64): vô ích cho trace, tốn đĩa và chậm bộ lọc."""
    if isinstance(obj, str):
        if len(obj) > OMIT_ABOVE and not any(c.isspace() for c in obj[:2000]):
            return f"[OMITTED:blob {len(obj)} ký tự]"
        return obj
    if isinstance(obj, list):
        return [_drop_blobs(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _drop_blobs(v) for k, v in obj.items()}
    return obj


def copy_redacted(src: str, dest: Path, counts: Counter[str]) -> None:
    """Lọc từng dòng JSONL rồi đổi tên nguyên tử vào `dest` (không bao giờ ghi đè).

    Ghi ra file tạm cùng thư mục: bị ngắt giữa chừng (báo thức, kill) thì chỉ
    còn file .tmp, không để lại bản dở mang tên thật.
    """
    if dest.exists():
        return
    inp = open(src, encoding="utf-8", errors="replace")  # mở nguồn TRƯỚC: thiếu file thì không để lại thư mục rỗng
    _mkdir_private(dest.parent)
    now = time.time()
    for old in dest.parent.glob(".tmp-*"):  # SIGKILL bỏ lại file tạm; dọn bản cũ hơn 1 giờ
        try:
            if now - old.stat().st_mtime > 3600:
                old.unlink()
        except OSError:
            pass
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=".jsonl")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out, inp:
            for raw in inp:
                raw = raw.rstrip("\n")
                if not raw:
                    continue
                try:
                    obj = R.redact_obj(_drop_blobs(json.loads(raw)), counts)
                    out.write(json.dumps(obj, ensure_ascii=False) + "\n")
                except ValueError:
                    # Dòng không phải JSON: lọc như văn bản, đóng gói để vẫn là JSONL hợp lệ.
                    out.write(json.dumps({"unparsed": R.redact_text(raw, counts)}, ensure_ascii=False) + "\n")
        try:
            os.link(tmp, dest)  # link thất bại nếu dest đã có: không đè
        except FileExistsError:
            pass
        except OSError:
            # FS không hỗ trợ hard link (exFAT, SMB...): đổi tên, chấp nhận race rất hẹp.
            if not dest.exists():
                os.rename(tmp, dest)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ═════════════════════════════════════════════════════════════════════════
#  Điểm vào
# ═════════════════════════════════════════════════════════════════════════


def handle(ev: dict[str, Any], base: Path) -> None:
    hook = ev.get("hook_event_name") or ""
    sid = str(ev.get("session_id") or "unknown")
    safe_sid = "".join(c for c in sid if c.isalnum() or c in "-_")[:64] or "unknown"
    _mkdir_private(base)
    st = os.lstat(base)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise RuntimeError("trace dir không phải thư mục của user hiện tại")
    os.chmod(base, 0o700)  # sửa cả thư mục có sẵn với quyền lỏng hơn
    counts: Counter[str] = Counter()

    if hook in ("Stop", "SubagentStop"):
        rec = build_turn(ev, hook)
        rec = R.redact_obj(rec, counts)
        # Cắt SAU khi lọc: cắt trước có thể xẻ đôi một token làm nửa còn lại không khớp mẫu nào.
        for k, n in (("prompt", MAX_PROMPT), ("agent_prompt", MAX_PROMPT),
                     ("last_assistant_message", MAX_ASSISTANT), ("diff_stat", MAX_DIFFSTAT)):
            if isinstance(rec.get(k), str):
                rec[k] = _clip(rec[k], n)
        rec["redactions"] = dict(counts)
        _append_line(base / "turns.jsonl", json.dumps(rec, ensure_ascii=False))
        atp = ev.get("agent_transcript_path")
        if hook == "SubagentStop" and atp and ev.get("agent_id") and os.path.isfile(atp):
            aid = "".join(c for c in str(ev["agent_id"]) if c.isalnum() or c in "-_")[:64]
            if aid:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                # Subagent tiếp tục (cùng agent_id) tạo bản mới thay vì bị bỏ qua.
                copy_redacted(atp, base / "sessions" / safe_sid / f"subagent-{aid}.{stamp}.jsonl", counts)
    elif hook == "SessionEnd":
        tp = ev.get("transcript_path")
        if tp and os.path.exists(tp):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            # Resume ghi tiếp cùng session_id: mỗi lần kết thúc là một bản riêng.
            copy_redacted(tp, base / "sessions" / f"{safe_sid}.{stamp}.jsonl", counts)
        prune_old(base)  # sau khi chép: dọn lỗi không được làm mất bản sao mới
    # Sự kiện khác: bỏ qua im lặng.


def main() -> int:
    # Cổng opt-in: hook nằm trong settings.json dùng chung nên chạy trên máy mọi người
    # clone repo, mà transcript có thể chứa dữ liệu Jira công ty. Mặc định TẮT; ai muốn
    # ghi vết tự bật ở .claude/settings.local.json (gitignore): {"env": {"CLAUDE_TRACE_ENABLED": "1"}}.
    if os.environ.get("CLAUDE_TRACE_ENABLED") != "1":
        return 0
    base: Path | None = None
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(ALARM_SECONDS["SessionEnd"])  # trần cho cả việc đọc stdin; thu hẹp sau khi biết sự kiện
    try:
        ev = json.loads(sys.stdin.read() or "{}")
        if not isinstance(ev, dict):
            raise ValueError("stdin không phải object")
        hook = ev.get("hook_event_name") or ""
        signal.alarm(ALARM_SECONDS.get(hook, ALARM_DEFAULT))
        base = trace_dir(os.environ.get("CLAUDE_PROJECT_DIR"))
        handle(ev, base)
    except BaseException as exc:  # kể cả _Timeout và KeyboardInterrupt: không bao giờ vỡ phiên
        signal.alarm(0)  # tắt báo thức trước, kẻo nổ giữa lúc ghi lỗi
        log_error(base, "main", exc)
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())

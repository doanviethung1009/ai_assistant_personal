"""Test cho trace-hook.py và trace_redact.py. Chạy:

    python3 -m unittest discover -s .claude/hooks/tests -v

Mọi "secret" ở đây là DỮ LIỆU GIẢ, không dùng secret thật. Mỗi test chạy hook
như harness: tiến trình con, JSON qua stdin, HOME và CLAUDE_TRACE_DIR trỏ vào
thư mục tạm để không đụng ~/.claude thật.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOKS))
import trace_redact as R  # noqa: E402

HOOK = HOOKS / "trace-hook.py"

FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJmYWtlIjoidGVzdCJ9.ZmFrZXNpZ25hdHVyZQ"
FAKE_LONG = "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6"  # base64 giả >32
FAKE_ATLASSIAN = "ATATT3xFfGF0FAKEFAKEFAKEFAKEFAKEFAKEFAKE=ABCD1234"


class RedactTests(unittest.TestCase):
    def setUp(self) -> None:
        R.reset_cache()

    def red(self, s: str) -> str:
        return R.redact_text(s, Counter())

    def test_bearer_and_basic(self) -> None:
        out = self.red("curl -H 'Authorization: Bearer abcDEF123456789xyz' https://x")
        self.assertNotIn("abcDEF123456789xyz", out)
        out = self.red("Basic dXNlcjpwYXNzd29yZDEyMw==")
        self.assertNotIn("dXNlcjpwYXNz", out)

    def test_authorization_header_json(self) -> None:
        out = self.red('{"Authorization": "Basic QUJDMTIzNDU2Nzg5"}')
        self.assertNotIn("QUJDMTIzNDU2Nzg5", out)

    def test_jwt(self) -> None:
        self.assertNotIn("ZmFrZXNpZ25hdHVyZQ", self.red(f"token eyJ is {FAKE_JWT} ok"))

    def test_atlassian(self) -> None:
        self.assertNotIn("FAKEFAKE", self.red(f"jira {FAKE_ATLASSIAN}"))

    def test_named_env_vars(self) -> None:
        for name in ("API_KEY", "IMPORT_COMMIT_SECRET", "INTEGRATION_SECRET_KEY",
                     "POSTGRES_PASSWORD", "OPENAI_API_KEY", "JIRA_TOKEN", "MY_SECRET", "PASSWORD"):
            out = self.red(f"{name}=hunter2-fake-value")
            self.assertNotIn("hunter2-fake-value", out, name)
            self.assertIn("[REDACTED", out)

    def test_json_pairs_text(self) -> None:
        out = self.red('{"api_key": "fake value with spaces", "name": "keep"}')
        self.assertNotIn("fake value with spaces", out)
        self.assertIn("keep", out)

    def test_long_token_near_keyword(self) -> None:
        out = self.red(f"the token is {FAKE_LONG} done")
        self.assertNotIn(FAKE_LONG, out)

    def test_email(self) -> None:
        out = self.red("liên hệ someone.fake@example.com nhé")
        self.assertNotIn("someone.fake", out)

    def test_url_password(self) -> None:
        out = self.red("postgresql+asyncpg://app:fakepw99@db:5432/x")
        self.assertNotIn("fakepw99", out)
        self.assertIn("@db:5432", out)

    def test_private_key_block(self) -> None:
        out = self.red("-----BEGIN PRIVATE KEY-----\nFAKEBODY\n-----END PRIVATE KEY-----")
        self.assertNotIn("FAKEBODY", out)

    def test_dotenv_literal_values(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".env").write_text("SOME_PLAIN_NAME=plainfakeval-77\n# c\n")
            old = os.environ.get("CLAUDE_PROJECT_DIR")
            os.environ["CLAUDE_PROJECT_DIR"] = d
            try:
                R.reset_cache()
                self.assertNotIn("plainfakeval-77", self.red("dòng log plainfakeval-77 ở đây"))
            finally:
                if old is None:
                    del os.environ["CLAUDE_PROJECT_DIR"]
                else:
                    os.environ["CLAUDE_PROJECT_DIR"] = old
                R.reset_cache()

    def test_keeps_token_counts_and_benign(self) -> None:
        obj = {"usage": {"input_tokens": 12, "output_tokens": 3}, "note": "TOKEN=$TOKEN", "x": "plain text"}
        out = R.redact_obj(obj, Counter())
        self.assertEqual(out["usage"], {"input_tokens": 12, "output_tokens": 3})
        self.assertEqual(out["x"], "plain text")
        self.assertIn("$TOKEN", out["note"])

    def test_json_key_redaction_on_structure(self) -> None:
        out = R.redact_obj({"headers": {"X-Api-Key": "fake123"}, "password": "pw"}, Counter())
        self.assertEqual(out["headers"]["X-Api-Key"], "[REDACTED:json-key]")
        self.assertEqual(out["password"], "[REDACTED:json-key]")

    def test_names_only_in_placeholder(self) -> None:
        out = self.red("API_KEY=hunter2-fake-value")
        self.assertRegex(out, r"\[REDACTED:[a-z-]+\]")

    def test_performance_on_big_blob(self) -> None:
        # Không có "key " đứng trước: tiền tố đó từng khiến _NEAR_KEYWORD che sạch blob
        # trước và test đo được 0 giây (không chứng minh gì).
        for blob in (" " + "a" * 200_000, " " + "token" * 40_000, "A1" * 1_500_000):
            t = time.time()
            self.red(blob)
            self.assertLess(time.time() - t, 5)

    def test_review_findings_forms(self) -> None:
        cases = {
            'curl -d "{\\"password\\":\\"FakePw1234\\"}"': "FakePw1234",
            "curl -u admin:FakePassw0rd https://h": "FakePassw0rd",
            "mysql -pFakeMy5qlPw db": "FakeMy5qlPw",
            "cli --password FakeArgPw123": "FakeArgPw123",
            "DB_PASS=FakeDbPass99": "FakeDbPass99",
            "pass: FakePassCol99": "FakePassCol99",
            "Cookie: sid=FakeCookie12345": "FakeCookie12345",
            "redis://:FakeRedisPw@host:6379": "FakeRedisPw",
            "PASSWORD=$ecretFake123": "ecretFake123",
            "API_KEY=<FakeKey>123": "FakeKey",
            '{"password":"%FakePct123"}': "FakePct123",
            "mật khẩu là FakeVi123, ok": "FakeVi123",
            "key=" + "Ab1_" * 10 + "Ab1_Ab1=": "Ab1_Ab1_Ab1_",
            "https://gitlab.com glpat-FakeFakeFakeFakeFake1": "FakeFakeFakeFake",
        }
        for text, leak in cases.items():
            self.assertNotIn(leak, self.red(text), text)
        obj = R.redact_obj({"api_keys": ["FAKElist12345"], "credentials": {"user": "u", "pw": "FakeNested1"}}, Counter())
        self.assertNotIn("FAKElist12345", json.dumps(obj))
        self.assertNotIn("FakeNested1", json.dumps(obj))

    def test_no_overredaction_of_benign_text(self) -> None:
        for text in ("TOKEN=$TOKEN", "x passed=true", "bypass the check", "ssh -p 2222 host",
                     "docker compose up -d", '"session_id": "abc-123"'):
            self.assertEqual(self.red(text), text, text)


class HookProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.trace = self.root / "trace"
        self.home = self.root / "home"
        self.home.mkdir()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "fake-branch", str(self.repo)], check=True)
        (self.repo / "a.txt").write_text("x\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t.t",
                        "commit", "-qm", "i"], check=True)
        (self.repo / "a.txt").write_text("x\ny\n")
        self.transcript = self.root / "t.jsonl"
        lines = [
            {"type": "user", "isSidechain": False, "message": {"role": "user", "content": "prompt cũ"}},
            {"type": "user", "isSidechain": False, "message": {"role": "user",
             "content": f"hãy dùng API_KEY=hunter2-fake-value và {FAKE_JWT}"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "INTEGRATION_SECRET_KEY=hunter2-fake-value"}]}},
            {"type": "assistant", "message": {"usage": {"input_tokens": 5}}},
        ]
        self.transcript.write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_hook(self, event: dict | str, trace: Path | None = None, extra_env: dict | None = None):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TRACE_DIR"}
        env.update(HOME=str(self.home), CLAUDE_TRACE_DIR=str(trace or self.trace),
                   CLAUDE_PROJECT_DIR=str(self.repo))
        env.update(extra_env or {})
        data = event if isinstance(event, str) else json.dumps(event)
        return subprocess.run([sys.executable, str(HOOK)], input=data, capture_output=True,
                              text=True, env=env, timeout=30)

    def mode(self, p: Path) -> int:
        return stat.S_IMODE(p.stat().st_mode)

    def stop_event(self, name: str = "Stop") -> dict:
        return {"hook_event_name": name, "session_id": "sess-1", "cwd": str(self.repo),
                "transcript_path": str(self.transcript), "prompt_id": "p1",
                "last_assistant_message": "xong, token Bearer abcDEF123456789xyz"}

    def test_stop_writes_one_redacted_line(self) -> None:
        r = self.run_hook(self.stop_event())
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        f = self.trace / "turns.jsonl"
        lines = f.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["session_id"], "sess-1")
        self.assertEqual(rec["git_branch"], "fake-branch")
        self.assertIn("a.txt", rec["diff_stat"])
        self.assertIn("hãy dùng", rec["prompt"])  # lấy prompt thật, bỏ tool_result
        blob = f.read_text()
        for leak in ("hunter2-fake-value", "ZmFrZXNpZ25hdHVyZQ", "abcDEF123456789xyz"):
            self.assertNotIn(leak, blob)
        self.assertEqual(self.mode(f), 0o600)
        self.assertEqual(self.mode(self.trace), 0o700)

    def test_append_never_truncates(self) -> None:
        self.run_hook(self.stop_event())
        self.run_hook(self.stop_event("SubagentStop"))
        self.assertEqual(len((self.trace / "turns.jsonl").read_text().splitlines()), 2)

    def test_session_end_copy_is_redacted_and_private(self) -> None:
        ev = {"hook_event_name": "SessionEnd", "session_id": "sess-1", "cwd": str(self.repo),
              "transcript_path": str(self.transcript), "reason": "other"}
        r = self.run_hook(ev)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        files = list((self.trace / "sessions").glob("sess-1.*.jsonl"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text()
        for leak in ("hunter2-fake-value", "ZmFrZXNpZ25hdHVyZQ"):
            self.assertNotIn(leak, text)
        self.assertEqual(len(text.splitlines()), 5)
        for line in text.splitlines():
            json.loads(line)
        self.assertEqual(self.mode(files[0]), 0o600)
        self.assertEqual(self.mode(self.trace / "sessions"), 0o700)
        self.assertEqual(list((self.trace / "sessions").glob(".tmp-*")), [])

    def test_subagent_transcript_copied(self) -> None:
        ev = self.stop_event("SubagentStop")
        ev.update(agent_id="ag1", agent_type="Explore", agent_transcript_path=str(self.transcript))
        self.run_hook(ev)
        files = list((self.trace / "sessions" / "sess-1").glob("subagent-ag1.*.jsonl"))
        self.assertEqual(len(files), 1)
        self.assertEqual(self.mode(files[0]), 0o600)
        text = files[0].read_text()
        self.assertNotIn("hunter2-fake-value", text)
        self.assertNotIn("ZmFrZXNpZ25hdHVyZQ", text)
        rec = json.loads((self.trace / "turns.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["agent_prompt"], "prompt cũ")  # dòng user đầu của transcript subagent

    def test_missing_agent_transcript_leaves_no_trace(self) -> None:
        ev = self.stop_event("SubagentStop")
        ev.update(agent_id="ag2", agent_type="", agent_transcript_path=str(self.root / "khong-co.jsonl"))
        r = self.run_hook(ev)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertFalse((self.trace / "sessions").exists())
        self.assertFalse((self.trace / "errors.log").exists())

    def test_prompt_skips_system_notifications_and_prefers_prompt_id(self) -> None:
        rows = [
            {"type": "user", "promptId": "p-real", "origin": {"kind": "human"},
             "message": {"role": "user", "content": "yêu cầu thật"}},
            {"type": "user", "promptId": "p-other", "origin": {"kind": "human"},
             "message": {"role": "user", "content": "prompt khác"}},
            {"type": "user", "origin": {"kind": "task-notification"},
             "message": {"role": "user", "content": "<task-notification>xong</task-notification>"}},
            {"type": "user", "message": {"role": "user", "content": "<ci-monitor-event>x</ci-monitor-event>"}},
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta"}},
        ]
        self.transcript.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        ev = self.stop_event()
        ev["prompt_id"] = "p-real"
        self.run_hook(ev)
        rec = json.loads((self.trace / "turns.jsonl").read_text())
        self.assertEqual(rec["prompt"], "yêu cầu thật")
        ev["prompt_id"] = "không-khớp"
        self.run_hook(ev)
        rec = json.loads((self.trace / "turns.jsonl").read_text().splitlines()[-1])
        self.assertEqual(rec["prompt"], "prompt khác")  # lùi về prompt người gần nhất

    def test_existing_content_preserved_and_perms_tightened(self) -> None:
        self.trace.mkdir(mode=0o755)
        self.trace.chmod(0o755)
        f = self.trace / "turns.jsonl"
        f.write_text('{"old": 1}\n')
        f.chmod(0o644)
        self.run_hook(self.stop_event())
        lines = f.read_text().splitlines()
        self.assertEqual((len(lines), lines[0]), (2, '{"old": 1}'))
        self.assertEqual((self.mode(f), self.mode(self.trace)), (0o600, 0o700))

    def test_secret_at_clip_boundary_not_leaked(self) -> None:
        # Token nằm đúng ranh giới cắt 20000: phải lọc trước khi cắt.
        secret = "hunter2-fake-boundary-value"
        prompt = "a" * (20_000 - 8) + f" API_KEY={secret}"
        self.transcript.write_text(json.dumps(
            {"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
        self.run_hook(self.stop_event())
        self.assertNotIn("boundary-value", (self.trace / "turns.jsonl").read_text())

    def test_session_end_never_overwrites_existing_destination(self) -> None:
        ev = {"hook_event_name": "SessionEnd", "session_id": "sess-1", "transcript_path": str(self.transcript)}
        self.run_hook(ev)
        f = next((self.trace / "sessions").glob("sess-1.*.jsonl"))
        f.write_text("giữ nguyên\n")
        self.run_hook(ev)  # có thể cùng giây hoặc khác giây: bản đầu không bao giờ bị đổi
        self.assertEqual(f.read_text(), "giữ nguyên\n")

    def test_hook_does_not_modify_repo(self) -> None:
        before = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        self.run_hook(self.stop_event())
        after = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                               capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_refuses_trace_dir_inside_repo(self) -> None:
        inside = self.repo / "trace"
        r = self.run_hook(self.stop_event(), trace=inside)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertFalse(inside.exists())

    # ── Lỗi không được làm hook thoát khác 0 ──────────────────────────
    def test_broken_json(self) -> None:
        r = self.run_hook("{không phải json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_empty_stdin(self) -> None:
        self.assertEqual(self.run_hook("").returncode, 0)

    def test_non_object_json(self) -> None:
        self.assertEqual(self.run_hook("[1,2]").returncode, 0)

    def test_missing_transcript(self) -> None:
        ev = self.stop_event()
        ev["transcript_path"] = str(self.root / "khong-co.jsonl")
        r = self.run_hook(ev)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        rec = json.loads((self.trace / "turns.jsonl").read_text())
        self.assertIsNone(rec["prompt"])  # vẫn ghi dòng tóm tắt
        ev["hook_event_name"] = "SessionEnd"
        self.assertEqual(self.run_hook(ev).returncode, 0)

    def test_unwritable_dir(self) -> None:
        ro = self.root / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        try:
            r = self.run_hook(self.stop_event(), trace=ro / "sub")
            self.assertEqual((r.returncode, r.stdout), (0, ""))
            self.assertEqual(list(ro.iterdir()), [])  # (chạy bằng root thì test này không chứng minh gì)
        finally:
            ro.chmod(0o700)

    def test_unknown_event_is_ignored(self) -> None:
        r = self.run_hook({"hook_event_name": "Whatever", "session_id": "s"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_hostile_session_id_stays_inside_dir(self) -> None:
        ev = {"hook_event_name": "SessionEnd", "session_id": "../../evil", "transcript_path": str(self.transcript)}
        self.run_hook(ev)
        self.assertFalse((self.root / "evil").exists())
        self.assertTrue(any((self.trace / "sessions").iterdir()))


if __name__ == "__main__":
    unittest.main()

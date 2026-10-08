"""Bảo đảm log của app luôn bắt được trong test.

Vì sao có file này: `alembic.fileConfig` (chạy trong fixture `migrated_db`, cùng process pytest)
mặc định TẮT mọi logger đã tồn tại. Khi đó `caplog` rỗng và mọi assert kiểu "token không có
trong log" đúng vì log rỗng chứ không vì không rò. `migrations/env.py` đã đặt
`disable_existing_loggers=False`; test này giữ cho lỗi đó không quay lại.
"""

from __future__ import annotations

import logging

import pytest


@pytest.mark.db
async def test_app_loggers_are_not_disabled_by_migrations(
    client: object, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    names = sorted(n for n in logging.root.manager.loggerDict if n.startswith("app."))
    assert names, "không tìm thấy logger app.* nào, điều kiện kiểm tra đã vô nghĩa"
    disabled = [n for n in names if logging.getLogger(n).disabled]
    assert disabled == [], f"logger bị tắt (caplog sẽ rỗng): {disabled}"
    for name in names:
        logging.getLogger(name).warning("log-capture-probe %s", name)
    for name in names:
        assert f"log-capture-probe {name}" in caplog.text, name

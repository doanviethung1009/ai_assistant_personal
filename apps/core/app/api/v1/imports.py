"""Endpoint nhập hàng loạt từ file JSON vào Postgres.

══════════════════════════════════════════════════════════════════════
 CẢNH BÁO: CÁC ENDPOINT NÀY GHI ĐÈ BẢN GHI ĐÃ TỒN TẠI.

 Chúng KHÔNG xoá bản ghi, KHÔNG nhận `raw_payload`. Nội dung file (note, payload
 event, mô tả task) là dữ liệu không đáng tin. `dry_run` mặc định `true`; nhập thật
 bắt buộc kèm `expect_replaced` lấy từ báo cáo dry-run. Xem
 services/import_service.py và docs/specs/import-json-to-postgres.md.
══════════════════════════════════════════════════════════════════════

Body được đọc thô (không để FastAPI tự parse) vì cần ba thứ mà parse tự động
không cho: giới hạn kích thước theo luồng (413 trước khi nạp hết vào RAM),
sha256 của đúng byte client gửi (ghi vào `import_runs`), và bỏ BOM của file xuất
từ Windows.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.api.deps import ImportSecretHeader, SessionDep, guard_import_secret
from app.schemas.imports import AiLogsEnvelope, DataFileEnvelope, ImportReport
from app.services import import_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

MAX_BODY_BYTES = 10 * 1024 * 1024
_BOM = b"\xef\xbb\xbf"

DryRunQuery = Annotated[
    bool,
    Query(description="true (mặc định): chạy thử rồi ROLLBACK, không ghi gì."),
]
ExpectReplacedQuery = Annotated[
    int | None,
    Query(
        ge=0,
        description=(
            "Bắt buộc khi dry_run=false: số bản ghi sẽ bị ghi đè, lấy từ báo cáo dry-run. "
            "Lệch số thực tế thì huỷ."
        ),
    ),
]
ExpectSha256Query = Annotated[
    str | None,
    Query(
        min_length=64,
        max_length=64,
        pattern="^[0-9a-fA-F]{64}$",
        description=(
            "Bắt buộc khi dry_run=false: `file_sha256` trong báo cáo dry-run. Chứng minh "
            "file nhập thật chính là file đã kiểm tra, không chỉ trùng số lượng."
        ),
    ),
]
IncludePersonalQuery = Annotated[
    bool,
    Query(
        description=(
            "false (mặc định): task đang `personal` trong DB KHÔNG bị file ghi đè "
            "(đếm `skipped_personal`). true: cho phép ghi đè cả task cá nhân."
        )
    ),
]


def _body_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Mô tả request body trong OpenAPI, vì handler đọc body thô nên FastAPI không tự suy ra."""
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": model.model_json_schema()}},
        }
    }


async def _read_body(request: Request) -> bytes:
    """Đọc body theo luồng, dừng ngay khi vượt 10 MB (413)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="File vượt giới hạn 10 MB.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="File vượt giới hạn 10 MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse[M: BaseModel](body: bytes, model: type[M]) -> M:
    payload = body[len(_BOM) :] if body.startswith(_BOM) else body
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        # RecursionError: JSON lồng sâu hàng chục nghìn tầng (`[[[[...`) làm
        # json.loads tràn stack; không bắt thì thành 500 thay vì 422.
        raise HTTPException(status_code=422, detail="Body không phải JSON hợp lệ.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Body phải là một object JSON.")
    try:
        return model.model_validate(data)
    except RecursionError as exc:
        raise HTTPException(status_code=422, detail="JSON lồng quá sâu.") from exc
    except PydanticValidationError as exc:
        # Chỉ trả vị trí và loại lỗi, không echo lại giá trị trong file.
        details = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False, include_context=False)[:20]
        ]
        raise HTTPException(status_code=422, detail="; ".join(details)) from exc


def _guard_commit(
    request: Request,
    dry_run: bool,
    expect_replaced: int | None,
    expect_sha256: str | None,
    secret: str | None,
) -> None:
    """Rào chắn cho nhập THẬT, chạy trước khi đọc body hay chạm DB.

    Thứ tự: tham số bắt buộc (422), rồi mật khẩu (403). Web không có đăng nhập và
    API key đã nằm trong server env của web, nên chỉ API key thì bất kỳ ai mở được
    `/data` đều ghi đè được dữ liệu; mật khẩu nhập là lớp thứ hai.
    Dry-run chỉ đọc nên không cần mật khẩu.
    """
    if dry_run:
        return
    if expect_replaced is None or not expect_sha256:
        raise HTTPException(
            status_code=422,
            detail="dry_run=false bắt buộc có expect_replaced và expect_sha256.",
        )
    guard_import_secret(request, secret)


@router.post(
    "/verify-secret",
    status_code=204,
    summary="Kiểm mật khẩu nhập (X-Import-Secret), không ghi gì",
)
async def verify_secret(request: Request, import_secret: ImportSecretHeader = None) -> Response:
    """Cho web xác minh mật khẩu THẬT trước khi tải URL (tới 20 MB) hay parse Excel.

    Nếu chỉ kiểm cú pháp, người gọi Server Action giả chưa biết mật khẩu vẫn gây tốn
    băng thông/CPU. Không đọc body, không chạm DB; 403 như mọi đường dùng mật khẩu nhập.
    """
    guard_import_secret(request, import_secret)
    return Response(status_code=204)


@router.post(
    "/datafile",
    response_model=ImportReport,
    summary="Nhập builder-data.json (GHI ĐÈ bản ghi đã có, không xoá)",
    openapi_extra=_body_schema(DataFileEnvelope),
)
async def import_datafile(
    request: Request,
    session: SessionDep,
    dry_run: DryRunQuery = True,
    expect_replaced: ExpectReplacedQuery = None,
    expect_sha256: ExpectSha256Query = None,
    import_secret: ImportSecretHeader = None,
    include_personal: IncludePersonalQuery = False,
) -> ImportReport:
    _guard_commit(request, dry_run, expect_replaced, expect_sha256, import_secret)
    body = await _read_body(request)
    envelope = _parse(body, DataFileEnvelope)
    return await import_service.import_datafile(
        session,
        envelope,
        include_personal=include_personal,
        dry_run=dry_run,
        expect_replaced=expect_replaced,
        expect_sha256=expect_sha256,
        file_sha256=hashlib.sha256(body).hexdigest(),
    )


@router.post(
    "/ai-logs",
    response_model=ImportReport,
    summary="Nhập ai-logs.json (GHI ĐÈ bản ghi đã có, không xoá)",
    openapi_extra=_body_schema(AiLogsEnvelope),
)
async def import_ai_logs(
    request: Request,
    session: SessionDep,
    dry_run: DryRunQuery = True,
    expect_replaced: ExpectReplacedQuery = None,
    expect_sha256: ExpectSha256Query = None,
    import_secret: ImportSecretHeader = None,
) -> ImportReport:
    _guard_commit(request, dry_run, expect_replaced, expect_sha256, import_secret)
    body = await _read_body(request)
    envelope = _parse(body, AiLogsEnvelope)
    return await import_service.import_ai_logs(
        session,
        envelope,
        dry_run=dry_run,
        expect_replaced=expect_replaced,
        expect_sha256=expect_sha256,
        file_sha256=hashlib.sha256(body).hexdigest(),
    )

"""Quy tắc đồng bộ tag (docs/specs/tag-rules.md).

Cố ý nằm ở `/tag-rules`, KHÔNG phải `/tags/rules`: `/tags/{name:path}` nuốt mọi đường con nên
`DELETE /tags/rules/<id>` sẽ bị hiểu là xoá tag tên `rules/<id>`.

Rule chỉ được TẠO gián tiếp qua đổi tên/xoá tag (`api/v1/tags.py`); ở đây chỉ đọc và gỡ.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUserDep, SessionDep, require_permission
from app.core.permissions import Permission
from app.schemas.common import Page
from app.schemas.tag import TagRuleRead
from app.services import tag_rule_service

router = APIRouter(prefix="/tag-rules", tags=["tag-rules"])


@router.get(
    "",
    response_model=Page[TagRuleRead],
    summary="Danh sách quy tắc đồng bộ tag, sắp theo tag nguồn",
    description=(
        "Mọi user đã đăng nhập đọc được: rule ảnh hưởng task work mà ai cũng thấy, member cần "
        "biết vì sao tag Jira không hiện. Không trả email người tạo."
    ),
)
async def list_tag_rules(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> Page[TagRuleRead]:
    rows, total = await tag_rule_service.list_rules(session, limit=limit, offset=offset)
    items = [
        TagRuleRead(
            id=rule.id,
            source_tag=rule.source_tag,
            target_tag=rule.target_tag,
            created_by_user_id=rule.created_by_user_id,
            created_by_name=name,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
        for rule, name in rows
    ]
    return Page[TagRuleRead](items=items, total=total, limit=limit, offset=offset)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.TASK_WRITE_ANY_WORK))],
    summary="Gỡ quy tắc (lần đồng bộ tới tag nguồn sẽ quay lại)",
)
async def delete_tag_rule(
    rule_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> Response:
    await tag_rule_service.delete_rule(session, user, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

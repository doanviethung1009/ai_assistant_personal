from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.tag import TagChangeResponse, TagRename, TagStat
from app.services import tag_service

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get(
    "/stats",
    response_model=list[TagStat],
    summary="Mọi tag đang dùng kèm số task và note",
    description=(
        "Chỉ đếm bản ghi chưa xoá mềm mà user nhìn thấy: task work, task personal của mình, "
        "note của mình. Số tag riêng biệt nhỏ nên không phân trang."
    ),
)
async def tag_stats(session: SessionDep, user: CurrentUserDep) -> list[TagStat]:
    return await tag_service.list_stats(session, user)


@router.patch(
    "/{name:path}",
    response_model=TagChangeResponse,
    summary="Đổi tên tag",
    description=(
        "Đổi trên mọi task/note user được phép sửa (task work cần `task:write_any_work`). "
        "Tên mới đã tồn tại trên cùng bản ghi thì gộp. 404 nếu không bản ghi nào dùng tag; "
        "409 nếu tên mới trùng tên cũ."
    ),
)
async def rename_tag(
    name: str, body: TagRename, session: SessionDep, user: CurrentUserDep
) -> TagChangeResponse:
    return await tag_service.rename(session, user, name, body.new_name)


@router.delete(
    "/{name:path}",
    response_model=TagChangeResponse,
    summary="Xoá tag khỏi mọi task/note được phép sửa",
)
async def delete_tag(name: str, session: SessionDep, user: CurrentUserDep) -> TagChangeResponse:
    return await tag_service.delete(session, user, name)

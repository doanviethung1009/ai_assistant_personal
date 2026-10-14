from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import bind_display_tz, current_user
from app.api.v1 import (
    auth,
    imports,
    integrations,
    me,
    notes,
    projects,
    settings,
    system,
    tasks,
)
from app.core.security import require_api_key

# Mọi endpoint dưới /api/v1 đều yêu cầu API key (chứng minh request đến từ web). Health nằm
# ngoài prefix này để probe của Prometheus gọi được mà không cần khoá.
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

# Chỉ API key, KHÔNG JWT: lúc đăng nhập người dùng chưa có JWT.
api_router.include_router(auth.router)

# Mọi router còn lại đòi thêm JWT người dùng (user `active`, session_version khớp). Quyền chi tiết
# theo ma trận spec auth-multiuser mục 3.4 khai ở từng route bằng `require_permission`.
user_router = APIRouter(dependencies=[Depends(current_user), Depends(bind_display_tz)])
user_router.include_router(me.router)
user_router.include_router(tasks.router)
user_router.include_router(projects.router)
user_router.include_router(notes.router)
user_router.include_router(system.router)
user_router.include_router(imports.router)
user_router.include_router(settings.router)
user_router.include_router(integrations.router)
api_router.include_router(user_router)

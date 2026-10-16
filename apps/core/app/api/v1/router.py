from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import current_user, require_password_current
from app.api.v1 import (
    admin,
    auth,
    imports,
    integrations,
    me,
    notes,
    projects,
    settings,
    system,
    tag_rules,
    tags,
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
user_router = APIRouter(dependencies=[Depends(current_user)])
# Chỉ `/me` và `/me/password` đi được khi tài khoản đang bị ép đổi mật khẩu.
user_router.include_router(me.router)

# ═══════════════════════════════════════════════════════════════════════
#  MỌI ROUTER MỚI MẶC ĐỊNH PHẢI NẰM Ở ĐÂY. Đặt ngoài `active_router` là bỏ qua việc ép đổi mật
#  khẩu: tài khoản vừa được cấp mật khẩu tạm đọc được dữ liệu mà chưa đổi mật khẩu.
# ═══════════════════════════════════════════════════════════════════════
active_router = APIRouter(dependencies=[Depends(require_password_current)])
active_router.include_router(tasks.router)
active_router.include_router(projects.router)
active_router.include_router(notes.router)
active_router.include_router(tags.router)
active_router.include_router(tag_rules.router)
active_router.include_router(system.router)
active_router.include_router(imports.router)
active_router.include_router(settings.router)
active_router.include_router(integrations.router)
active_router.include_router(admin.router)
user_router.include_router(active_router)
api_router.include_router(user_router)

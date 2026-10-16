#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Đưa MỘT nhánh task lên VM dev (ai-dev-01) để xem backend thật, rồi trả về main.
#
#  Dùng:
#    scripts/agents/dev-vm-branch.sh status
#    scripts/agents/dev-vm-branch.sh deploy <nhánh> [T<N>] [--allow-migration]
#    scripts/agents/dev-vm-branch.sh restore
#
#  VÌ SAO CÓ SCRIPT NÀY: máy local không có Docker nên kiểm chứng chính là VM dev. Nhưng
#  /srv/builder-ai/dev chứa DB THẬT và chỉ có MỘT checkout, nên phải có luật:
#    1. Một nhánh tại một thời điểm: khoá ~/dev-branch.lock trên VM (ghi nhánh, task, giờ).
#       Task khác muốn deploy phải chờ `restore`, không được đè.
#    2. Luôn `make backup` (pg_dump ra backups/ trên VM) TRƯỚC khi đổi nhánh.
#    3. Từ chối nhánh có migration mới (so với origin/main) trừ khi có --allow-migration:
#       `restore` chỉ đổi mã, KHÔNG downgrade schema, nên migration đã chạy vẫn nằm lại trong
#       DB thật. Muốn thử migration thì dùng dev-vm-smoke.sh (DB tạm), không dùng script này.
#    4. Từ chối khi checkout trên VM có thay đổi chưa commit (mất mã nếu đổi nhánh).
#    5. `restore` chỉ checkout lại `main` CỤC BỘ của VM, KHÔNG kéo origin/main: kéo main mới
#       có thể mang migration và đổi schema DB thật ngoài ý muốn. Nâng dev lên main mới là
#       việc riêng, có sao lưu, theo docs/PROXMOX_OPERATIONS.md.
#
#  GIỚI HẠN: container api mount ./apps/core nên tự reload theo nhánh mới. Container web là
#  image dựng sẵn (không mount mã), nên KHÔNG có mã web của nhánh. Xem web của nhánh bằng
#  `make devvm-web` ở worktree (chạy web local, gọi API dev qua tunnel).
#  Không bao giờ đẩy lên staging/prod: script chỉ nói chuyện với DEV_VM.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/../.."

SSH_KEY="${SSH_KEY:-$HOME/.ssh/ai_assistant_deploy}"
HOST="${DEV_VM:-deploy@192.168.100.201}"
DEV_DIR="/srv/builder-ai/dev"
# Nháy đơn để $HOME giữ nguyên chữ, rồi mở rộng trên VM (không phải ở máy local).
LOCK='$HOME/dev-branch.lock'
SSH=(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST")

die() { echo "LỖI: $*" >&2; exit 1; }
info() { echo "==> $*"; }

# Chờ api tự reload xong rồi gọi health; 200 mới coi là khoẻ.
health() {
  "${SSH[@]}" 'for i in $(seq 1 20); do
      code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health/ready || true)
      [ "$code" = 200 ] && { echo "health 200"; exit 0; }
      sleep 3
    done; echo "health KHÔNG đạt (lần cuối: $code)"; exit 1'
}

cmd="${1:-}"
case "$cmd" in
  status)
    "${SSH[@]}" "cd $DEV_DIR && echo \"nhánh trên VM: \$(git branch --show-current) @ \$(git rev-parse --short HEAD)\" \
      && (cat $LOCK 2>/dev/null && echo '(đang bị khoá bởi nhánh trên)' || echo 'không có khoá') \
      && git status --porcelain | sed 's/^/thay đổi chưa commit: /' \
      && docker compose -p builder-dev ps --format '{{.Service}} {{.Status}}'"
    ;;

  deploy)
    BRANCH="${2:-}"; [[ -n "$BRANCH" ]] || die "thiếu tên nhánh. Dùng: deploy <nhánh> [T<N>] [--allow-migration]"
    TASK="${3:-}"; [[ "$TASK" == --* ]] && TASK=""
    ALLOW_MIG=0; for a in "$@"; do [[ "$a" == "--allow-migration" ]] && ALLOW_MIG=1; done
    [[ "$BRANCH" != "main" ]] || die "dùng 'restore' để về main"
    [[ "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]] || die "tên nhánh chứa ký tự lạ"

    # Chỉ deploy nhánh ĐÃ push: VM lấy mã từ origin, không nhận mã chưa commit của máy local.
    git fetch -q origin main "$BRANCH" 2>/dev/null || die "origin chưa có nhánh $BRANCH (đã push chưa?)"
    MIG="$(git diff --name-only "origin/main...origin/$BRANCH" -- apps/core/migrations | grep -c . || true)"
    if [[ "$MIG" -gt 0 && "$ALLOW_MIG" -ne 1 ]]; then
      die "nhánh có $MIG file migration mới: schema DB thật sẽ đổi và 'restore' không hoàn tác. Thử migration bằng scripts/patches/dev-vm-smoke.sh. Biết rủi ro thì thêm --allow-migration."
    fi

    info "kiểm khoá và checkout trên VM"
    "${SSH[@]}" "set -e; cd $DEV_DIR
      if [ -s $LOCK ]; then
        cur=\$(cat $LOCK)
        case \"\$cur\" in *\"branch=$BRANCH \"*) echo 'khoá đã thuộc nhánh này, tiếp tục';;
          *) echo \"VM dev đang bị khoá: \$cur\" >&2; exit 2;; esac
      fi
      [ -z \"\$(git status --porcelain)\" ] || { echo 'checkout trên VM có thay đổi chưa commit' >&2; git status --short >&2; exit 3; }"

    info "sao lưu DB dev (make backup)"
    "${SSH[@]}" "cd $DEV_DIR && mkdir -p backups && make backup 2>&1 | tail -1"

    info "checkout $BRANCH"
    "${SSH[@]}" "set -e; cd $DEV_DIR
      git fetch -q origin '$BRANCH'
      git checkout -q '$BRANCH'
      git reset -q --hard 'origin/$BRANCH'
      echo \"branch=$BRANCH task=${TASK:--} since=\$(date -u +%FT%TZ) \" > $LOCK
      git log --oneline -1"
    health
    echo "Xong. Dev đang chạy $BRANCH. Nhớ: scripts/agents/dev-vm-branch.sh restore"
    ;;

  restore)
    info "trả VM dev về main"
    "${SSH[@]}" "set -e; cd $DEV_DIR
      [ -z \"\$(git status --porcelain)\" ] || { echo 'checkout trên VM có thay đổi chưa commit, dừng' >&2; exit 3; }
      git checkout -q main
      rm -f $LOCK
      git log --oneline -1"
    health
    ;;

  *)
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac

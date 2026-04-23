#!/usr/bin/env bash
# Migration script: github.com/duhd-vnpay/litellm -> git.vnpay.vn/duhd/litellm
# Chạy sau khi đã tạo empty repo trên GitLab nội bộ.
# Usage: bash deploy/vnpay/migrate-to-gitlab.sh [--dry-run]

set -euo pipefail

GITLAB_URL="https://git.vnpay.vn/duhd/litellm.git"
GITHUB_URL="https://github.com/duhd-vnpay/litellm.git"
UPSTREAM_URL="https://github.com/BerriAI/litellm.git"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  echo "[DRY RUN] — chỉ in lệnh, không thực thi"
fi

run() {
  echo "+ $*"
  [[ $DRY_RUN -eq 0 ]] && "$@"
}

echo "=== 1. Kiểm tra trạng thái worktree ==="
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: worktree có uncommitted changes. Commit hoặc stash trước."
  git status --short
  exit 1
fi

echo "=== 2. Rename remote hiện tại ==="
if git remote | grep -q "^origin$"; then
  run git remote rename origin github-old
fi

echo "=== 3. Add GitLab remote làm origin ==="
if ! git remote | grep -q "^origin$"; then
  run git remote add origin "$GITLAB_URL"
fi

echo "=== 4. Add upstream (BerriAI) nếu chưa có ==="
if ! git remote | grep -q "^upstream$"; then
  run git remote add upstream "$UPSTREAM_URL"
fi

echo "=== 5. Push tất cả branches + tags lên GitLab ==="
run git push origin --all
run git push origin --tags

echo "=== 6. Set upstream tracking cho branch hiện tại ==="
CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
run git branch --set-upstream-to="origin/$CUR_BRANCH" "$CUR_BRANCH"

echo "=== 7. Verify ==="
run git remote -v
run git fetch origin

cat <<'EOF'

Xong phần local git. Việc phải làm trên GitLab UI:

1. Settings → Repository → Mirroring repositories:
   - URL: https://github.com/BerriAI/litellm.git
   - Mirror direction: Pull
   - Mirror branches matching regex: ^(main|v[0-9]+\.[0-9]+\.[0-9]+.*)$ (tuỳ ý)

2. Settings → General → Visibility: Private

3. Settings → Members: thêm team VNPay (maintainer role)

4. Settings → Protected branches: bảo vệ `main`

5. CI/CD Variables (masked + protected): KUBECONFIG, SPLUNK_HEC_TOKEN, ...

Việc phải làm ngoài repo:

- ArgoCD Application: đổi spec.source.repoURL → git.vnpay.vn/duhd/litellm
- Port .github/workflows/ → .gitlab-ci.yml (nếu cần)
- Update docs/wiki nội bộ link về repo mới
- GitHub fork: Settings → Archive (giữ 30 ngày rollback)
EOF

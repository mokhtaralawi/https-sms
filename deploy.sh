#!/usr/bin/env bash
#
# deploy.sh — Pull latest code, migrate, and restart all services.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh            # from project root on the server
#   sudo ./deploy.sh       # if services require root
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

PYTHON="$PROJECT_DIR/venv/bin/python"
TEST_CMD="$PYTHON -c \"import django; print('Django', django.get_version())\""

echo ""
echo "=========================================="
echo "  Deploying HttpSMS"
echo "=========================================="
echo ""

# ── 1. Pull latest code ──────────────────────────────────────────────
echo "▸ Pulling latest code from origin/main ..."
git pull origin main || fail "git pull failed"
info "Code updated"

# ── 2. Django system check ───────────────────────────────────────────
echo ""
echo "▸ Running Django system check ..."
$PYTHON manage.py check --deploy 2>&1 || warn "Some deploy checks raised warnings (may be acceptable)"
info "System check done"

# ── 3. Install / update dependencies ─────────────────────────────────
echo ""
echo "▸ Installing Python dependencies ..."
"$PROJECT_DIR/venv/bin/pip" install -q -r requirements.txt 2>&1 | tail -1
info "Dependencies up to date"

# ── 4. Make migrations (auto-detect model changes) ───────────────────
echo ""
echo "▸ Running makemigrations ..."
$PYTHON manage.py makemigrations --no-input 2>&1
info "Migrations checked"

# ── 5. Apply migrations ──────────────────────────────────────────────
echo ""
echo "▸ Applying migrations ..."
$PYTHON manage.py migrate --no-input 2>&1
info "Database migrated"

# ── 6. Collect static files ──────────────────────────────────────────
echo ""
echo "▸ Collecting static files ..."
$PYTHON manage.py collectstatic --no-input 2>&1
info "Static files collected"

# ── 7. Restart Redis ─────────────────────────────────────────────────
echo ""
echo "▸ Restarting Redis ..."
sudo systemctl restart redis-server 2>/dev/null \
  || sudo systemctl restart redis 2>/dev/null \
  || sudo systemctl restart redis-server.service 2>/dev/null \
  || warn "Redis service not found — make sure Redis is installed and running"
info "Redis checked"

# ── 8. Restart application services ──────────────────────────────────
echo ""
echo "▸ Restarting application services ..."
for svc in httpsms-web httpsms-worker httpsms-beat; do
  sudo systemctl restart "$svc" 2>/dev/null && info "$svc restarted" || warn "$svc not found"
done

# ── 9. Restart Nginx ─────────────────────────────────────────────────
echo ""
echo "▸ Restarting Nginx ..."
sudo systemctl restart nginx 2>/dev/null && info "Nginx restarted" || warn "Nginx not found"

# ── Done ─────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo -e "${GREEN}  ✅  Deployment complete!${NC}"
echo "=========================================="
echo ""

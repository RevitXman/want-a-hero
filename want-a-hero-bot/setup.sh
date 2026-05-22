#!/usr/bin/env bash
# =============================================================================
# setup.sh  —  One-shot installer for the Want-A-Hero bot on Ubuntu EC2
#
# Run as the ubuntu user (or any sudo-capable user):
#   chmod +x setup.sh && ./setup.sh
#
# What it does:
#   1. Updates apt packages
#   2. Installs Python 3.11+, pip, git, and other essentials
#   3. Creates a dedicated 'herobot' system user
#   4. Clones / copies the project to /opt/wantahero
#   5. Creates a Python venv and installs dependencies
#   6. Copies the systemd service file and enables it
# =============================================================================

set -euo pipefail

INSTALL_DIR="/opt/wantahero"
BOT_USER="herobot"
SERVICE_NAME="wantahero"
PYTHON="python3"

echo "============================================================"
echo "  Want-A-Hero Bot — Ubuntu EC2 Setup"
echo "============================================================"

# ── 1. System packages ────────────────────────────────────────────────────────
echo ""
echo "[1/6] Updating apt and installing dependencies..."
sudo apt-get update -y
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev

echo "      Python version: $($PYTHON --version)"

# ── 2. Dedicated system user ──────────────────────────────────────────────────
echo ""
echo "[2/6] Creating system user '${BOT_USER}'..."
if id "${BOT_USER}" &>/dev/null; then
    echo "      User '${BOT_USER}' already exists, skipping."
else
    sudo useradd --system --shell /usr/sbin/nologin --home-dir "${INSTALL_DIR}" "${BOT_USER}"
    echo "      Created user '${BOT_USER}'."
fi

# ── 3. Install directory ──────────────────────────────────────────────────────
echo ""
echo "[3/6] Setting up install directory at ${INSTALL_DIR}..."
sudo mkdir -p "${INSTALL_DIR}"/{data,logs,credentials}
sudo chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}"

# Copy project files from current directory to install directory
echo "      Copying project files..."
sudo rsync -av --exclude='.git' --exclude='.env' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.venv' \
    ./ "${INSTALL_DIR}/"

sudo chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}"

# ── 4. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "[4/6] Creating Python virtual environment..."
sudo -u "${BOT_USER}" $PYTHON -m venv "${INSTALL_DIR}/.venv"
sudo -u "${BOT_USER}" "${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${BOT_USER}" "${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
echo "      Dependencies installed."

# ── 5. Environment file ───────────────────────────────────────────────────────
echo ""
echo "[5/6] Checking for .env file..."
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    sudo cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
    sudo chown "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}/.env"
    sudo chmod 640 "${INSTALL_DIR}/.env"
    echo ""
    echo "  ⚠️  IMPORTANT: Edit ${INSTALL_DIR}/.env before starting the bot!"
    echo "      sudo nano ${INSTALL_DIR}/.env"
    echo ""
else
    echo "      .env already exists, skipping."
fi

# ── 6. Systemd service ────────────────────────────────────────────────────────
echo ""
echo "[6/6] Installing systemd service..."
sudo cp "${INSTALL_DIR}/systemd/${SERVICE_NAME}.service" \
    "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
echo "      Service enabled. It will start automatically on boot."
echo ""

# ── Done ──────────────────────────────────────────────────────────────────────
echo "============================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit your config:"
echo "       sudo nano ${INSTALL_DIR}/.env"
echo ""
echo "  2. (Optional) Add your Google service account key:"
echo "       sudo cp service_account.json ${INSTALL_DIR}/credentials/"
echo "       sudo chown ${BOT_USER}:${BOT_USER} ${INSTALL_DIR}/credentials/service_account.json"
echo ""
echo "  3. Start the bot:"
echo "       sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "  4. Check it's running:"
echo "       sudo systemctl status ${SERVICE_NAME}"
echo "       sudo journalctl -u ${SERVICE_NAME} -f"
echo "============================================================"

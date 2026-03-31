#!/bin/bash
#
# Deploy Inverter Control to Venus OS
#
# Prerequisites:
#   - SSH config with host 'Cerbo' pointing to Venus OS device
#   - SSH key authentication configured
#
# Usage: ./deploy.sh [SSH_HOST]
#

set -e

SSH_HOST="${1:-Cerbo}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE_DIR="/data/inverter_control"

echo "=============================================="
echo "  Deploying Inverter Control to Venus OS"
echo "=============================================="
echo "SSH Host: $SSH_HOST"
echo ""

# Create directories on remote
echo ">>> Creating directories..."
ssh "$SSH_HOST" "mkdir -p $REMOTE_DIR/web"

# Copy files
echo ">>> Copying Python files..."
scp "$SCRIPT_DIR/config.py" "$SSH_HOST:$REMOTE_DIR/"
scp "$SCRIPT_DIR/main.py" "$SSH_HOST:$REMOTE_DIR/"
scp "$SCRIPT_DIR/victron.py" "$SSH_HOST:$REMOTE_DIR/"
scp "$SCRIPT_DIR/homeassistant.py" "$SSH_HOST:$REMOTE_DIR/"
scp "$SCRIPT_DIR/web/__init__.py" "$SSH_HOST:$REMOTE_DIR/web/"
scp "$SCRIPT_DIR/web/server.py" "$SSH_HOST:$REMOTE_DIR/web/"
scp "$SCRIPT_DIR/install.sh" "$SSH_HOST:$REMOTE_DIR/"
scp "$SCRIPT_DIR/healthcheck.sh" "$SSH_HOST:$REMOTE_DIR/"

# Copy secrets if exists (not tracked by git)
if [ -f "$SCRIPT_DIR/secrets.py" ]; then
    echo ">>> Copying secrets..."
    scp "$SCRIPT_DIR/secrets.py" "$SSH_HOST:$REMOTE_DIR/"
fi

# Make executable
ssh "$SSH_HOST" "chmod +x $REMOTE_DIR/main.py $REMOTE_DIR/install.sh"

# Run install script
echo ""
echo ">>> Running install script..."
ssh "$SSH_HOST" "cd $REMOTE_DIR && ./install.sh"

echo ""
echo ">>> Checking service status..."
ssh "$SSH_HOST" "sleep 3 && svstat /service/inverter-control /service/inverter-healthcheck"

echo ""
echo "=============================================="
echo "  Deployment Complete!"
echo "=============================================="
echo ""
echo "Web interface: http://\$(ssh $SSH_HOST 'hostname -I | cut -d\" \" -f1'):8080"
echo ""
echo "To view error log:"
echo "  ssh $SSH_HOST 'tail -f /var/log/inverter-control.log'"
echo ""
echo "To view live output (stops service temporarily):"
echo "  ssh $SSH_HOST '/data/inverter_control/live.sh'"
echo ""

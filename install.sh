#!/bin/bash
# Install Radio Monitor on a Debian/Ubuntu system
set -euo pipefail

INSTALL_DIR="/opt/radio-monitor"

echo "=== Installing system dependencies ==="
apt update
apt install -y rtl-sdr python3 python3-venv python3-pip libportaudio2

echo "=== Setting up $INSTALL_DIR ==="
mkdir -p "$INSTALL_DIR"
cp -r radio_monitor/ "$INSTALL_DIR/"
cp config.yaml "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"

echo "=== Creating Python venv ==="
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "=== Setting up log directory ==="
mkdir -p /var/log/radio-monitor

echo "=== Installing systemd service ==="
cp radio-monitor.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit config:     nano $INSTALL_DIR/config.yaml"
echo "  2. Set frequency:   Use HackRF/SDR++ to find your radio channel"
echo "  3. Set ntfy topic:  Change 'radio-monitor-CHANGEME' to something unique"
echo "  4. Test with mic:   $INSTALL_DIR/venv/bin/python -m radio_monitor -c $INSTALL_DIR/config.yaml --test-mic"
echo "  5. Run with SDR:    $INSTALL_DIR/venv/bin/python -m radio_monitor -c $INSTALL_DIR/config.yaml"
echo "  6. Enable service:  systemctl enable --now radio-monitor"
echo ""
echo "Web dashboard:  http://$(hostname -I | awk '{print $1}'):5555"

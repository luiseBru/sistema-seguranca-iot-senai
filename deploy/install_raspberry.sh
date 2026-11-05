#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
ENV_FILE="/etc/default/seguranca-iot"

echo "Instalando dependencias do sistema..."
sudo apt update
sudo apt install -y mosquitto mosquitto-clients python3-venv

echo "Criando ambiente Python..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
mkdir -p "$APP_DIR/data"

echo "Configurando acesso a porta serial..."
sudo usermod -aG dialout "$APP_USER"

echo "Configurando Mosquitto local..."
sudo install -m 0644 "$APP_DIR/deploy/mosquitto-local.conf" /etc/mosquitto/conf.d/seguranca-local.conf

echo "Criando configuracao da aplicacao..."
sed "s|__APP_DIR__|$APP_DIR|g" "$APP_DIR/deploy/seguranca-iot.env.example" | sudo tee "$ENV_FILE" >/dev/null
sudo chmod 0644 "$ENV_FILE"

echo "Instalando servicos systemd..."
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" \
  "$APP_DIR/deploy/seguranca-api.service" | sudo tee /etc/systemd/system/seguranca-api.service >/dev/null
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" \
  "$APP_DIR/deploy/seguranca-publicador.service" | sudo tee /etc/systemd/system/seguranca-publicador.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable mosquitto seguranca-api seguranca-publicador
sudo systemctl restart mosquitto
sudo systemctl restart seguranca-api seguranca-publicador

echo
echo "Instalacao concluida."
echo "Edite $ENV_FILE se a porta do Arduino nao for /dev/ttyACM0."
echo "Depois, reinicie os servicos:"
echo "  sudo systemctl restart seguranca-api seguranca-publicador"
echo "Abra no navegador: http://$(hostname -I | awk '{print $1}'):8000"

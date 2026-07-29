# Xiaomi X10 HomeControl

Small Flask + MQTT bridge for a Xiaomi X10 vacuum.

## What runs

- `app.py`: web UI and JSON API on port `5050` by default.
- `xiaomi_x10_bridge.py`: background worker that polls the robot with `miiocli`, publishes state to MQTT, and handles command topics.
- `xiaomi_x10_map.py`: downloads and renders map data when the bridge detects a changed map object.

## Required files for the HC server

Copy these to the server:

- `app.py`
- `config.py`
- `xiaomi_x10_api.py`
- `xiaomi_x10_bridge.py`
- `xiaomi_x10_map.py`
- `templates/`
- `x10_maps/` with at least `maps_index.json` and `xiaomi_cloud_auth.json`
- `Xiaomi-cloud-tokens-extractor/token_extractor.py`
- `requirements.txt`
- `deploy/`

## Setup

```bash
cd /opt/xiaomi-x10
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` for the HC server paths, MQTT host, robot IP, token, and `X10_MIIOCLI`.

## Manual start

```bash
set -a
. ./.env
set +a
python3 app.py
```

In a second terminal:

```bash
set -a
. ./.env
set +a
python3 xiaomi_x10_bridge.py
```

Open `http://HC_SERVER_IP:5050/xiaomi_x10`.

## systemd

Example unit files are in `deploy/systemd/`.

```bash
sudo cp deploy/systemd/xiaomi-x10-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xiaomi-x10-web.service xiaomi-x10-bridge.service
```

# Mower manual-control WebSocket contract

Status: HC client implemented. Canonical safety and compatibility rules are in
`ROVER_HC_CONTRACT.md` v2.1.0; this file only expands the WebSocket exchange.

Endpoint: `ws://<mower-esp-ip>/ws`

Subprotocol/version: `homecontrol.mower.manual.v1`

All frames are UTF-8 JSON. Manual movement is deliberately not carried over
MQTT. MQTT `cmd/stop` remains an independent emergency-stop path.

## Client frames

```json
{"type":"claim","client":"hc-<random>","protocol":"homecontrol.mower.manual.v1"}
{"type":"drive","seq":1,"forward":1200,"turn":-250}
{"type":"heartbeat","seq":2}
{"type":"stop","seq":3}
{"type":"release","seq":4}
```

- `forward` and `turn` are signed integer RPM values in `-6000..6000`.
  Out-of-range input is rejected and causes a stop; it is not silently clamped.
- The HC sends drive frames when the cruise speed or steering correction changes.
- The HC sends a heartbeat every 250 ms while it owns control.
- Page hide, connection close, explicit disable and the STOP button send `stop`.

## Server frames

```json
{"type":"claimed","client":"hc-...","deadman_ms":700}
{"type":"ack","seq":1,"forward":1200,"turn":-250}
{"type":"state","owner":"hc-...","armed":true,"forward":1200,"turn":-250}
{"type":"error","code":"busy","message":"manual control already owned"}
```

## Required ESP safety behavior

- Accept one owner only, using the existing remote-session/control-owner rules.
- Do not enable movement before a successful `claim` and normal STM safety checks.
- Clamp every command and update `lastClientCommandMs` on valid drive/heartbeat frames.
- Send `HEADING TARGET CANCEL` before the first non-zero manual drive command.
- Execute `RC STOP`, release ownership and close the socket if no valid frame arrives within 700 ms.
- Execute `RC STOP` on WebSocket disconnect, malformed command flood or `release`.
- `stop` zeros manual drive but retains ownership; global MQTT stop also releases ownership.
- Clear the owner immediately on `release` and whenever the owning socket disconnects; do not wait for a new claim.
- Never resume a previous command after reconnect.
- Keep MQTT emergency stop operational even while WebSocket owns manual control.

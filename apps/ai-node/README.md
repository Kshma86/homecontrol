# HomeControl AI Node

Portable remote LLM node for the larger Ubuntu AI server.

## Install on the AI server

1. Copy this directory to the AI server, for example `~/homecontrol-ai-node`.
2. Copy `.env.example` to `.env` and adjust ports/bind address if needed.
3. Start CPU mode:

```bash
docker compose up -d
```

4. Start NVIDIA GPU mode:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

5. Optional browser UI:

```bash
docker compose --profile ui up -d
```

6. Optional Gitea for HomeControl config repositories:

```bash
mkdir -p /mnt/hc-backup/gitea
docker compose --profile git up -d gitea
```

Default Gitea ports:

- Web UI: `http://192.168.1.2:3002`
- SSH: `2222`

The default data directory is `/mnt/hc-backup/gitea`.

## HomeControl settings

Set these in the HomeControl `infra/.env` on the mini PC:

```env
AI_NODE_NAME=Big AI Server
AI_NODE_HOST=192.168.1.x
AI_NODE_MAC=aa:bb:cc:dd:ee:ff
AI_NODE_SSH_USER=ubuntu
AI_NODE_STACK_DIR=~/homecontrol-ai-node
AI_NODE_NET_IFACE=enp4s0
AI_NODE_POWER_ENTITY_ID=121
AI_NODE_POWER_OFF_DELAY_SEC=300
AI_NODE_OLLAMA_URL=http://192.168.1.x:11434
AI_NODE_OPENWEBUI_URL=http://192.168.1.x:3001
```

Then rebuild/restart the HomeControl backend:

```bash
docker compose up -d --build backend
```

After that, the AI tab can wake the remote host, check SSH/Ollama status, control the remote compose stack, and connect HomeControl AI to the remote Ollama endpoint.

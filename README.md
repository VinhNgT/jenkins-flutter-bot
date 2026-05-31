<div align="center">
  <img src="apps/tg-bot/frontend-admin/public/favicon.svg" width="64" height="64" alt="Jenkins Flutter Bot" />
  <h1>Jenkins Flutter Bot</h1>
  <p>A self-hosted microservice CI/CD ecosystem — Telegram Mini Apps trigger Flutter builds on Jenkins and deliver APKs through Google Drive.</p>

  [![Build & Push Docker Images](https://github.com/VinhNgT/jenkins-flutter-bot/actions/workflows/build-images.yml/badge.svg)](https://github.com/VinhNgT/jenkins-flutter-bot/actions/workflows/build-images.yml)
</div>

---

## Architecture

```mermaid
graph TD
    subgraph users["Users"]
        TU["Telegram User"]
        BA["Browser Admin"]
    end

    subgraph public["Gateway Ingress Boundary"]
        CF["cloudflared (Tunnel)"]
        GW["gateway (Caddy Ingress)"]
    end

    subgraph ops["Core Infrastructure"]
        BOT["tg-bot :9090"]
        SH["service-hub :9000"]
    end

    subgraph managed["Managed Services"]
        BM["build-manager :9010"]
        FM["file-manager :9092"]
        AGT["agent-control :9091"]
    end

    subgraph external["External Services"]
        JNK["jenkins :8080 ★"]
        GD["Google Drive API"]
    end

    TU -- "Web App / HTTPS" --> CF
    CF --> GW
    BA -- "Localhost :8880" --> GW
    GW -- "/webapp & /webapp-admin" --> BOT
    BOT -- "polls / sends notifications" --> TU
    BOT -- "proxies config / VPN API" --> SH
    SH -. "manages configuration of" .-> managed

    BOT -- "stateless proxy / stream" --> BM
    BM -- "trigger / status / logs" --> JNK
    JNK -- "dispatches" --> AGT
    BM -- "polls" --> JNK
    BM -- "delegates builds / queries history" --> FM
    BM -- "vpn tunnel command" --> AGT
    FM -- "OAuth & Drive upload" --> GD
```

| Service | Port | Exposed | Role |
|---------|------|---------|------|
| `service-hub` | 9000 | No | Headless configuration orchestrator — config proxy and service lifecycle controls |
| `jenkins` | 8080 | Yes | Standard Jenkins controller (dev/testing — can be external) |
| `tg-bot` | 9090 | No | Unified gateway serving both Telegram Mini Apps (`/webapp` and `/webapp-admin`), proxying administrative requests, and running Telegram bot polling |
| `agent-control` | 9091 | No | Jenkins inbound agent with Flutter/Android SDKs, OpenVPN management + control API |
| `file-manager` | 9092 | No | Storage backend — Google Drive OAuth, build log, retention enforcement, ephemeral/log_only storage |
| `build-manager` | 9010 | No | Build orchestration — triggers Jenkins builds, tracks job state persistently, and delegates APK files to and queries history from file-manager |
| `gateway` | 80 | Yes | Caddy Ingress Gateway — unified path-based routing for `/webapp` and `/webapp-admin` to `tg-bot`. Host maps `8880:80` in dev |
| `cloudflared` | — | No | Cloudflare Tunnel — secure HTTPS tunnel connecting local gateway to Cloudflare |

---

## Quick Start

```bash
git clone https://github.com/VinhNgT/jenkins-flutter-bot.git
cd jenkins-flutter-bot/infra
./compose.sh up -d --build
```

Open **http://localhost:8880/webapp-admin** (best-effort standalone browser support or through Telegram client) and follow the **[Setup Guide](docs/setup-guide.md)** to configure Jenkins, Telegram, and Google Drive.

> [!NOTE]
> Both frontends are designed natively as **Telegram Mini Apps** to run inside the Telegram client. Direct access via standard standalone desktop browsers is supported on a **best-effort basis only**, utilizing standard browser storage and a fallback platform provider for local development and verification.

> **Production:** Pre-built images are on GHCR — use `./compose.sh prod up -d`. See the setup guide for details.

---

## Apps

| App | Description | Docs |
|-----|-------------|------|
| [tg-bot](apps/tg-bot/) | Unified Telegram gateway & Mini Apps — serves user/admin frontends, handles proxy APIs, handles slash commands and webhooks | [README](apps/tg-bot/README.md) |
| [service-hub](apps/service-hub/) | Headless operational core — environment settings orchestrator and service control APIs | [README](apps/service-hub/README.md) |
| [build-manager](apps/build-manager/) | Build orchestration — Jenkins trigger, persistent job state tracking, SSE build streams | [README](apps/build-manager/README.md) |
| [file-manager](apps/file-manager/) | Storage backend — Google Drive OAuth, build log, retention | [README](apps/file-manager/README.md) |
| [agent-control](apps/agent-control/) | Jenkins agent control wrapper + OpenVPN management | [README](apps/agent-control/README.md) |
| [mock-jenkins](apps/mock-jenkins/) | Dev/test mock — simulates Jenkins + agent-control APIs | [README](apps/mock-jenkins/README.md) |

## Libraries

| Library | Description | Docs |
|---------|-------------|------|
| [config-core](libs/config-core/) | Pydantic settings base classes, secret masking, and environment validation utilities | [README](libs/config-core/README.md) |
| [platform-core](libs/platform-core/) | Preact cross-platform settings storage, primary button context, hooks, and normalized capability adapters | — |
| [tg-core-preact](libs/tg-core-preact/) | Telegram WebApp SDK context provider, viewport sizing, and theme parameter synchronization hooks | — |
| [tg-ui-preact](libs/tg-ui-preact/) | High-fidelity Telegram UI Preact component library and stylesheet | — |

---

## License

This project is private. All rights reserved.


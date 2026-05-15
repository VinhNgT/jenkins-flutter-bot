<div align="center">
  <img src="apps/config-hub/src/config_hub/static/favicon.svg" width="64" height="64" alt="Jenkins Flutter Bot" />
  <h1>Jenkins Flutter Bot</h1>
  <p>A self-hosted microservice CI/CD ecosystem — Telegram triggers Flutter builds on Jenkins and delivers APKs through Google Drive.</p>

  [![Build & Push Docker Images](https://github.com/VinhNgT/jenkins-flutter-bot/actions/workflows/build-images.yml/badge.svg)](https://github.com/VinhNgT/jenkins-flutter-bot/actions/workflows/build-images.yml)
</div>

---

## Architecture

```mermaid
graph TD
    subgraph Users
        TU["Telegram User"]
        BA["Browser Admin"]
        TA["Telegram Admin"]
    end

    subgraph Management
        CH["config-hub :9000 (exposed)"]
        TAB["tg-admin-bot (internal)"]
    end

    subgraph Managed Services
        BOT["tg-bot :9090 (internal)"]
        AGT["flutter-agent :9091 (internal)"]
        FM["file-manager :9092 (internal)"]
        BM["build-manager :9010 (internal)"]
    end

    JNK["jenkins :8080 (exposed)"]

    TU -- polling --> BOT
    BA -- ":9000" --> CH
    TA -- polling --> TAB

    CH -- "/control/*" --> BOT
    CH -- "/control/*" --> AGT
    CH -- "/control/*" --> FM
    CH -- "/control/*" --> BM
    TAB -- "HTTP API" --> CH

    BOT -- "REST trigger" --> BM
    BM -- "REST trigger" --> JNK
    JNK -- "dispatches build" --> AGT
    AGT -- "webhook (build result)" --> BOT
    BOT -- "upload APK" --> FM
```

| Service | Port | Exposed | Role |
|---------|------|---------|------|
| `config-hub` | 9000 | Yes | Central operational hub — config proxy, service control, web dashboard |
| `jenkins` | 8080 | Yes | Jenkins controller (dev/testing — can be external) |
| `tg-bot` | 9090 | No | Telegram bot — slash commands, webhook receiver |
| `flutter-agent` | 9091 | No | Jenkins inbound agent with Flutter/Android SDKs |
| `file-manager` | 9092 | No | Storage backend — Drive OAuth, APK upload/download |
| `build-manager` | 9010 | No | Build orchestration — Jenkins trigger, job tracking |
| `tg-admin-bot` | — | No | Headless Telegram admin bot (HTTP client to config-hub) |

---

## Quick Start

```bash
git clone https://github.com/VinhNgT/jenkins-flutter-bot.git
cd jenkins-flutter-bot/infra
./compose.sh up -d --build
```

Open **http://localhost:9000** and follow the **[Setup Guide](docs/setup-guide.md)** to configure Jenkins, Telegram, and Google Drive.

> **Production:** Pre-built images are on GHCR — use `./compose.sh prod up -d`. See the setup guide for details.

---

## Apps

| App | Description | Docs |
|-----|-------------|------|
| [tg-jenkins-bot](apps/tg-jenkins-bot/) | Telegram bot — slash-command interface, webhook receiver, Drive upload | [README](apps/tg-jenkins-bot/README.md) |
| [config-hub](apps/config-hub/) | Central operational hub — config proxy, service control, web dashboard | [README](apps/config-hub/README.md) |
| [build-manager](apps/build-manager/) | Build orchestration — Jenkins trigger, job/state tracking | [README](apps/build-manager/README.md) |
| [file-manager](apps/file-manager/) | Storage backend — Google Drive OAuth, APK upload/download links | [README](apps/file-manager/README.md) |
| [tg-admin-bot](apps/tg-admin-bot/) | Headless Telegram admin bot — proxies to config-hub API | [README](apps/tg-admin-bot/README.md) |
| [agent-control](apps/agent-control/) | HTTP control wrapper for the Jenkins agent subprocess | [README](apps/agent-control/README.md) |
| [mock-jenkins](apps/mock-jenkins/) | Dev/test mock — simulates Jenkins + agent-control APIs | [README](apps/mock-jenkins/README.md) |

## Libraries

| Library | Description | Docs |
|---------|-------------|------|
| [config-core](libs/config-core/) | Pydantic `BootstrapSettings` / `ServiceSettings` bases + declarative config framework | [README](libs/config-core/README.md) |

---

## License

This project is private. All rights reserved.

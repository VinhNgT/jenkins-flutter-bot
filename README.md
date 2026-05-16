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
    subgraph users["Users"]
        TU["Telegram User"]
        BA["Browser Admin"]
        TA["Telegram Admin"]
    end

    subgraph ops["Ops  (optional)"]
        CH["config-hub :9000 ★"]
        TAB["tg-admin-bot"]
    end

    subgraph managed["Managed Services"]
        BOT["tg-bot :9090"]
        BM["build-manager :9010"]
        FM["file-manager :9092"]
        AGT["flutter-agent :9091"]
    end

    JNK["jenkins :8080 ★"]

    TU -- polling --> BOT
    BA --> CH
    TA -- polling --> TAB
    TAB -. "HTTP API" .-> CH
    CH -. "configures & controls" .-> managed

    BOT -- trigger --> BM
    BM -- trigger --> JNK
    JNK -- dispatches --> AGT
    AGT -- webhook --> BM
    BM -- upload --> FM
    BM -- callback --> BOT
```

| Service | Port | Exposed | Role |
|---------|------|---------|------|
| `config-hub` | 9000 | Yes | Central operational hub — config proxy, service control, web dashboard |
| `jenkins` | 8080 | Yes | Jenkins controller (dev/testing — can be external) |
| `tg-bot` | 9090 | No | Telegram bot — slash commands, notification rendering |
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
| [tg-jenkins-bot](apps/tg-jenkins-bot/) | Telegram bot — slash-command interface, notification rendering | [README](apps/tg-jenkins-bot/README.md) |
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

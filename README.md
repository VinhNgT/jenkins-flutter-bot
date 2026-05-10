<div align="center">
  <img src="apps/config-ui/src/config_ui/static/favicon.svg" width="64" height="64" alt="Jenkins Flutter Bot" />
  <h1>Jenkins Flutter Bot</h1>
  <p>A self-hosted CI/CD ecosystem — Telegram triggers Flutter builds on Jenkins and delivers APKs through Google Drive.</p>

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
        CUI["config-ui :9000 (exposed)"]
        TAB["tg-admin-bot (internal)"]
    end

    subgraph Managed Services
        BOT["tg-bot :9090 (internal)"]
        AGT["flutter-agent :9091 (internal)"]
    end

    JNK["jenkins :8080 (exposed)"]

    TU -- polling --> BOT
    BA -- ":9000" --> CUI
    TA -- polling --> TAB

    CUI -- "/control/*" --> BOT
    CUI -- "/control/*" --> AGT
    TAB -- "/control/*" --> BOT
    TAB -- "/control/*" --> AGT

    BOT -- "REST trigger" --> JNK
    JNK -- "dispatches build" --> AGT
    AGT -- "webhook (build result)" --> BOT
```

| Service | Port | Exposed | Role |
|---------|------|---------|------|
| `tg-bot` | 9090 | No | Telegram bot + webhook receiver |
| `config-ui` | 9000 | Yes | Web dashboard — config, service control, Drive OAuth |
| `jenkins` | 8080 | Yes | Jenkins controller (dev/testing — can be external) |
| `flutter-agent` | 9091 | No | Jenkins agent with Flutter/Android SDKs |
| `tg-admin-bot` | — | No | Headless Telegram admin bot |

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
| [tg-jenkins-bot](apps/tg-jenkins-bot/) | Telegram bot — build trigger + webhook receiver + Drive upload | [README](apps/tg-jenkins-bot/README.md) |
| [config-ui](apps/config-ui/) | Web dashboard — config CRUD, service control, Drive OAuth | [README](apps/config-ui/README.md) |
| [tg-admin-bot](apps/tg-admin-bot/) | Headless Telegram admin bot — stack management fallback | [README](apps/tg-admin-bot/README.md) |
| [agent-control](apps/agent-control/) | HTTP control wrapper for the Jenkins agent subprocess | [README](apps/agent-control/README.md) |

## Libraries

| Library | Description | Docs |
|---------|-------------|------|
| [config-schema](libs/config-schema/) | Declarative `FieldDef` schema framework | [README](libs/config-schema/README.md) |
| [stack-manager](libs/stack-manager/) | Service control, Drive OAuth, env I/O, Jenkinsfile generation | [README](libs/stack-manager/README.md) |

---

## License

This project is private. All rights reserved.

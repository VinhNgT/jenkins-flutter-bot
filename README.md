# 🏗️ Jenkins Flutter Bot — Monorepo

[![Build & Push Docker Images](https://github.com/VinhNgT/jenkins-flutter-bot/actions/workflows/build-images.yml/badge.svg)](https://github.com/VinhNgT/jenkins-flutter-bot/actions/workflows/build-images.yml)

A monorepo for the Jenkins-based Flutter CI/CD ecosystem, including the Telegram bot trigger layer, config UI dashboard, agent control wrapper, and supporting infrastructure.

## Repository Structure

```text
├── apps/                       Deployable applications
│   ├── tg-jenkins-bot/         Python — Telegram bot that triggers Jenkins builds
│   ├── config-ui/              Python — Web dashboard for stack configuration
│   └── agent-control/          Python — HTTP control wrapper for the Jenkins agent
│
├── libs/                       Shared workspace libraries
│   └── config-schema/          Python — Declarative configuration schema framework
│
└── infra/                      Infrastructure & CI/CD
    └── jenkins/                Docker Compose stack, agent Dockerfile, controller Dockerfile
```

## Apps

| App | Language | Description |
|-----|----------|-------------|
| [tg-jenkins-bot](apps/tg-jenkins-bot/) | Python | Telegram bot that triggers Jenkins builds and uploads artifacts to Google Drive |
| [config-ui](apps/config-ui/) | Python | FastAPI dashboard for managing bot and agent configuration, Google Drive OAuth |
| [agent-control](apps/agent-control/) | Python | HTTP control wrapper for the Jenkins inbound agent process (start/stop/status) |

## Getting Started

📖 **See [docs/setup-guide.md](docs/setup-guide.md) for a complete step-by-step walkthrough** covering Jenkins setup, Telegram bot creation, Google Drive OAuth, and configuration.

### Quick Start

```bash
cd infra/jenkins
docker compose up -d --build
```

This builds and starts all four services. Open the config UI at **http://localhost:9000** to configure the stack, then follow the [setup guide](docs/setup-guide.md) to complete Jenkins, Telegram, and Google Drive configuration.

> **Note:** The `jenkins` service in docker-compose is a local development/testing convenience. In production, the stack can connect to an external Jenkins instance by pointing `JENKINS_URL` to it and removing the `jenkins` service from the compose file.

### Local Development

The repo uses a **uv workspace** with a single lockfile at the root:

```bash
# Install all workspace members
uv sync

# Run a specific app
uv run --package tg-jenkins-bot tg-jenkins-bot
uv run --package config-ui config-ui
uv run --package agent-control agent-control
```

## License

This project is private. All rights reserved.

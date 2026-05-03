# 🏗️ Jenkins Flutter Bot — Monorepo

A monorepo for the Jenkins-based Flutter CI/CD ecosystem, including the Telegram bot trigger layer, config UI dashboard, agent control wrapper, and supporting infrastructure.

## Repository Structure

```text
├── apps/                       Deployable applications
│   ├── tg-jenkins-bot/         Python — Telegram bot that triggers Jenkins builds
│   ├── config-ui/              Python — Web dashboard for stack configuration
│   └── agent-control/          Python — HTTP control wrapper for the Jenkins agent
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

### Full Stack (Recommended)

```bash
cd infra/jenkins
docker compose up -d
```

This starts Jenkins, the Telegram bot, the config UI, and the Flutter build agent. Open the config UI at `http://localhost:9000` to configure the stack.

> **Note:** The `jenkins` service in docker-compose is a local development/testing convenience. In production, the stack can connect to an external Jenkins instance by pointing `JENKINS_URL` to it and removing the `jenkins` service from the compose file.

### Local Development

Each app is self-contained with its own dependencies:

```bash
cd apps/tg-jenkins-bot
uv sync
uv run tg-jenkins-bot
```

## License

This project is private. All rights reserved.

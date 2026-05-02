# 🏗️ Jenkins Flutter Bot — Monorepo

A monorepo for the Jenkins-based Flutter CI/CD ecosystem, including the Telegram bot trigger layer, config UI dashboard, and supporting infrastructure.

## Repository Structure

```text
├── apps/                       Deployable applications
│   ├── tg-jenkins-bot/         Python — Telegram bot that triggers Jenkins builds
│   └── config-ui/              Python — Web dashboard for stack configuration
│
└── infra/                      Infrastructure & CI/CD
    └── jenkins/                Docker Compose stack, agent Dockerfile, controller Dockerfile
```

## Apps

| App | Language | Description |
|-----|----------|-------------|
| [tg-jenkins-bot](apps/tg-jenkins-bot/) | Python | Telegram bot that triggers Jenkins builds and uploads artifacts to Google Drive |
| [config-ui](apps/config-ui/) | Python | FastAPI dashboard for managing bot and agent configuration, Google Drive OAuth |

## Getting Started

### Full Stack (Recommended)

```bash
cd infra/jenkins
docker compose up -d
```

This starts Jenkins, the Telegram bot, the config UI, and the Flutter build agent. Open the config UI at `http://localhost:9000` to configure the stack.

### Local Development

Each app is self-contained with its own dependencies:

```bash
cd apps/tg-jenkins-bot
uv sync
uv run tg-jenkins-bot
```

## License

This project is private. All rights reserved.

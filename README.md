# 🏗️ Jenkins Flutter Bot — Monorepo

A monorepo for the Jenkins-based Flutter CI/CD ecosystem, including the Telegram bot trigger layer and supporting infrastructure.

## Repository Structure

```text
├── apps/                   Deployable applications
│   └── tg-jenkins-bot/     Python — Telegram bot that triggers Jenkins builds
│
├── infra/                  Infrastructure & CI/CD
│   ├── jenkins/            Jenkins pipeline definitions & shared libraries
│   └── scripts/            Deployment & utility scripts
│
└── docs/                   Project-wide documentation
```

## Apps

| App | Language | Description |
|-----|----------|-------------|
| [tg-jenkins-bot](apps/tg-jenkins-bot/) | Python | Telegram bot that triggers Jenkins builds and uploads artifacts to Google Drive |

## Getting Started

Each app is self-contained with its own dependencies and setup instructions. Navigate to the app directory and follow its `README.md`:

```bash
cd apps/tg-jenkins-bot
uv sync
uv run tg-jenkins-bot
```

## License

This project is private. All rights reserved.

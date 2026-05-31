---
trigger: always_on
description: Core architectural reference — project identity, repo layout, service topology, and hard constraints.
---

# Jenkins Flutter Bot — AI Agent Guide

Core architectural reference and principles for the **jenkins-flutter-bot** monorepo CI/CD ecosystem.

---

## 1. Project Overview & Repository Layout
A self-hosted CI/CD ecosystem: a Telegram Mini App triggers Flutter builds on Jenkins, delivering compiled APKs through Google Drive. The architecture is managed under a **uv Workspace**:
- **`apps/`**: Six containerized Python applications implementing microservice boundaries (with a seventh dev-only `mock-jenkins` simulator).
- **`libs/`**: Shared Preact/TypeScript and Pydantic core workspace libraries:
  - `config-core`: Base configuration schemas, secret masking, logging, and signature validation helpers.
  - `platform-core` / `tg-core-preact` / `tg-ui-preact`: High-fidelity, decoupled Preact UI and SDK platform hooks.
- **`infra/`**: Docker Compose deployment environments and Caddy gateway configurations.
- **`scripts/`**: Centralized developer utilities.

---

## 2. Microservice Service Roles
Public webapp traffic and administrative access are routed behind a single Ingress gateway:
- **`config-hub` (port 9000)**: Operational proxy and Admin Telegram Mini App (`/webapp-admin`). Proxies config mutations and service statuses.
- **`jenkins` (port 8080)**: Standard compilation controller (can be external).
- **`tg-jenkins-bot` (port 9090)**: Polling bot + web client endpoints (`/webapp`).
- **`agent-control` (port 9091)**: Inbound build agent with Android/Flutter SDKs.
- **`file-manager` (port 9092)**: Drive OAuth, log retention, and storage backends.
- **`build-manager` (port 9010)**: Jenkins pipeline triggers and active job tracking.
- **`gateway` (port 80)**: Caddy Ingress perimeter managing unified path routing.
- **`cloudflared`**: Cloudflare Tunnel providing secure inbound HTTPS ingress.

*Note: For the visual Mermaid architecture diagram, consult the authoritative root [README.md](file:///Users/victor/Desktop/jenkins-flutter-bot/README.md).*

---

## 3. High-Level Design Principles & Constraints
- **Thin Trigger Paradigm**: Python services act strictly as a thin coordination layer. Actual compilation, signing, and code execution must happen entirely inside Jenkins pipelines.
- **Service-Local Volumes**: No service mounts another service's storage volume.
- **Do NOT mount `docker.sock`** into any container to preserve host isolation.
- **Do NOT expose internal service ports to the host** — only Caddy (`80`) and Jenkins (`8880`/`8080` in dev) are host-facing.


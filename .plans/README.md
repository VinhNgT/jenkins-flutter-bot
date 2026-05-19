# Pipeline Integration Refactoring — Plan Index

Replaces the fragile webhook-driven Jenkins integration with a polling-based
system. Broken into 4 independent tasks that can be executed in sequence or
partially in parallel.

## Task Overview

| # | File | Summary | Dependencies |
|---|------|---------|-------------|
| 01 | [01-polling-based-build-completion.md](01-polling-based-build-completion.md) | Replace webhook with polling loop in build-manager | None |
| 02 | [02-mock-jenkins-polling-support.md](02-mock-jenkins-polling-support.md) | Update mock-jenkins to expose polling endpoints | Parallel with 01 |
| 03 | [03-agent-node-provisioning.md](03-agent-node-provisioning.md) | API-driven Jenkins node creation + secret retrieval | Independent |
| 04 | [04-agent-optional-pipeline-simplify.md](04-agent-optional-pipeline-simplify.md) | Profile-gate agent-control, simplify pipeline template | After 01 |

## Execution Order

```
01 ──┐
     ├──→ 04
02 ──┘

03 (independent, any time)
```

- **Tasks 01 + 02** can run in parallel (they touch different services)
- **Task 04** depends on 01 (needs self_url removal) and 02 (needs mock updated)
- **Task 03** is fully independent — do it anytime

## What Changes Per Service

| Service | Task 01 | Task 02 | Task 03 | Task 04 |
|---------|---------|---------|---------|---------|
| build-manager | ✏️ Major (polling loop, artifact download) | — | ✏️ New endpoint (provision) | — |
| mock-jenkins | — | ✏️ Major (remove webhook, add endpoints) | ✏️ Mock node APIs | — |
| config-hub | — | — | ✏️ Orchestration + UI | ✏️ Graceful degradation + template |
| docker-compose | — | — | — | ✏️ Profiles, env cleanup |
| tg-bot | — | — | — | — |
| file-manager | — | — | — | — |
| agent-control | — | — | — | — |

## Design Decisions (from brainstorm)

These decisions are final — the task files implement them:

1. **Polling over webhook** — build-manager polls Jenkins REST API
2. **Passive tagging** — `BOT_REQUEST_ID` as a parameter Jenkins ignores
3. **Always archive** — `archiveArtifacts` as default (no conditional logic)
4. **Artifact naming** — `{job_name}_{branch}_{YYYYMMDD_HHmmss}.apk`
5. **Provisioning split** — build-manager does Jenkins API, config-hub orchestrates
6. **Agent-control optional** — `profiles: [agent]` in Docker Compose
7. **API-driven node creation** — not JCasC, not Swarm plugin

# 🔧 Agent Control

An HTTP control wrapper for the Jenkins inbound agent subprocess. Provides a FastAPI control API (`/control/start`, `/control/stop`, `/control/restart`, `/control/status`, `/control/schema`) so config-ui and tg-admin-bot can manage the agent without Docker socket access.

## How It Works

`AgentManager` wraps the Jenkins inbound agent as a child process:

- **Start** spawns `/usr/local/bin/jenkins-agent` with a filtered environment (only Jenkins-specific vars are forwarded)
- **Stop** sends `SIGTERM`, waits 5 seconds, then `SIGKILL` if needed
- **Status** uses `process.poll()` to report running/stopped state

On startup failure, the FastAPI server stays running — the control API remains available for retries.

## Configuration

Agent configuration follows the same declarative schema system as all other services. Fields are declared in `schema.py` and resolved via the standard precedence chain.

The `JENKINS_URL` and `JENKINS_AGENT_NAME` are infrastructure fields — typically set in `docker-compose.yml`, not in the config-ui.

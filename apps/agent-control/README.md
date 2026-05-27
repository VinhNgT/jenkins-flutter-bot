# 🔧 Agent Control

An HTTP control wrapper for the Jenkins inbound agent subprocess. Provides a FastAPI control API so config-hub can manage the agent lifecycle, VPN connections, and configuration without Docker socket access.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/control/status` | GET | Returns running state and process info |
| `/control/start` | POST | Spawns the Jenkins inbound agent process |
| `/control/stop` | POST | Gracefully terminates the agent (SIGTERM → SIGKILL) |
| `/control/restart` | POST | Stop + start in sequence |
| `/control/schema` | GET | Returns the declarative config field schema |
| `/control/config` | GET | Returns current config values (secrets masked) |
| `/control/config` | PUT | Saves config values (deep merge) |
| `/control/vpn/status` | GET | VPN file and connection status |
| `/control/vpn/connect` | POST | Connect OpenVPN tunnel |
| `/control/vpn/disconnect` | POST | Disconnect OpenVPN tunnel |
| `/control/vpn/upload` | POST | Upload `.ovpn` config file |
| `/control/vpn/upload` | DELETE | Delete stored `.ovpn` config file |

## How It Works

`AgentManager` wraps the Jenkins inbound agent as a child process:

- **Start** spawns `/usr/local/bin/jenkins-agent` with a filtered environment (only Jenkins-specific vars are forwarded)
- **Stop** sends `SIGTERM`, waits 5 seconds, then `SIGKILL` if needed
- **Status** uses `process.poll()` to report running/stopped state

On startup failure, the FastAPI server stays running — the control API remains available for retries.

## VPN Management

`VpnManager` manages an OpenVPN client subprocess to connect the build agent to the private network hosting the GitLab server, enabling Jenkins to clone the Flutter source repository during builds.

- Build-manager orchestrates connect/disconnect around build sessions — VPN is only active during builds to minimize the connection window.
- A configurable safety timer (`vpn.max_connected_minutes`) auto-disconnects the VPN if build-manager fails to disconnect (crash, timeout, etc.).
- Requires the `NET_ADMIN` capability and `/dev/net/tun` device access in Docker.

## Configuration

Agent configuration follows the same declarative schema system as all other services. Fields are declared in `config.py` and resolved via the standard precedence chain:

```
JSON config file (dashboard) > Environment Variable > .env file > Hardcoded default
```

Config is stored at `/app/data/agent.json` inside the container (mounted from the `agent-data` volume).

### Infrastructure Fields (set in docker-compose, not the dashboard)

| Variable | Default | Description |
|----------|---------|-------------|
| `JENKINS_URL` | `http://jenkins:8080` | Jenkins controller URL |
| `JENKINS_AGENT_NAME` | `flutter-agent` | Node name registered in Jenkins |
| `JENKINS_WEB_SOCKET` | `true` | Use WebSocket transport |

### Runtime Fields (managed via the dashboard)

| Field | Description |
|-------|-------------|
| Agent Secret | The secret token from the Jenkins node configuration page |
| Max VPN Duration | Auto-disconnect safety timer (minutes) |


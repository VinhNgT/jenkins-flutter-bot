# Infrastructure & Environments

The `jenkins-flutter-bot` orchestrates its microservices using Docker Compose. The infrastructure configuration is centralized in the `infra/` directory, following standard Docker compose patterns.

## Directory Layout

```text
infra/
├── compose.env                  # Environment variable overrides (loaded by compose.sh)
├── compose.env.example          # Auto-generated template for compose.env
├── compose.sh                   # Runner script for all docker compose commands
├── docker-compose.yml           # Base environment (Dev - builds images locally)
├── docker-compose.prod.yml      # Production environment (Pulls GHCR images)
├── docker-compose.hybrid.yml    # Hybrid environment (Local builds + GHCR agent)
├── docker-compose.mock.yml      # Mock environment (Fake Jenkins for UI testing)
├── agent/                       # Build context for the `agent-control` container
│   └── Dockerfile
├── gateway/                     # Build context for the `gateway` (Caddy) container
│   ├── Caddyfile
│   └── Dockerfile
└── jenkins/                     # Build context for the local dev Jenkins container
    └── Dockerfile
```

## Running the Stack

Instead of running `docker compose` directly, always use the `compose.sh` runner script from the `infra/` directory. It automatically loads variables from `compose.env` and maps your command to the correct environment file.

### Environments

1. **Dev (Default)**: Builds everything locally from source and includes a local Jenkins.
   ```bash
   ./compose.sh up -d --build
   ```

2. **Production (`prod`)**: Pulls pre-built images from the GitHub Container Registry. Excludes Jenkins (expects you to connect to a real, external Jenkins instance). 
   ```bash
   IMAGE_TAG=latest ./compose.sh prod up -d
   ```
   *Note: You can deploy bleeding-edge snapshots by using `IMAGE_TAG=edge ./compose.sh prod up -d`.*

3. **Hybrid (`hybrid`)**: Builds the Python web applications locally, but pulls the massive `agent-control` image from GHCR to save compile time.
   ```bash
   ./compose.sh hybrid up -d --build
   ```

4. **Mock (`mock`)**: Replaces the `jenkins` and `agent-control` containers with a lightweight mock server. Excellent for UI/UX work without running JVM/Flutter processes.
   ```bash
   ./compose.sh mock up -d --build
   ```

## Config Hub Export / Import Relationship

The Config Hub provides an Export/Import feature (`jfb-config.tar.gz`) that is structurally mapped directly to the local file system and Docker named volumes.

When you download a config backup, the tarball contains:
- `infra/compose.env`
- `data/bot.json`
- `data/agent.json`
- `data/storage.json`
- `data/builds.json`

### Why This Structure?

1. **`infra/compose.env`**: By mirroring the repository structure within the archive, a user can extract the backup tarball directly over the repository root, and `compose.env` will natively land in the correct `infra/` folder.
2. **`data/*.json`**: These JSON files encapsulate the internal state of the hidden Docker named volumes (`bot-data`, `agent-data`, etc.). They cannot be natively overlaid via a filesystem extraction, which is why the Config Hub **Import** interface exists—to safely read these files from the archive and HTTP PUT them into the running containers' respective volumes via the `/control/config` endpoints.

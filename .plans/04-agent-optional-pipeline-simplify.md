# Task 04: Make Agent-Control Optional + Simplify Pipeline Template

Make agent-control an optional service (profile-gated in Docker Compose),
update config-hub to gracefully degrade when it's absent, simplify the
Jenkinsfile template, and clean up environment variables.

## Why

The system currently requires agent-control in every deployment. Users who
already have their own Jenkins agents (Scenario A) don't need it. Making
agent-control optional via Docker Compose profiles enables two deployment modes:

- **Scenario A** (own agents): 4 services — tg-bot, build-manager, file-manager, config-hub
- **Scenario B** (bundled agent): 5 services — above + agent-control

The Jenkinsfile template is also drastically simplified since polling (Task 01)
eliminates the entire webhook `post` block.

## Dependencies

**After:** Task 01 (self_url removal), Task 02 (mock-jenkins updated).
**Independent of:** Task 03 (provisioning).

## Scope

**Services:** config-hub, infrastructure files.
**Files affected:** docker-compose.yml, config-hub manager/services/dashboard, pipeline template.

## Implementation Steps

### Step 1: Docker Compose — profile-gate agent-control

**File:** `infra/docker-compose.yml`

#### Move agent-control to profile

Add `profiles: [agent]` to the agent-control service (lines 90-107):

```yaml
  agent-control:
    profiles:
      - agent                          # <-- ADD THIS
    platform: linux/amd64
    build:
      context: ..
      dockerfile: infra/Dockerfile.flutter-agent
    # ... rest unchanged
```

#### Remove agent-control from config-hub depends_on

Currently (line 63-67):
```yaml
    depends_on:
      - tg-jenkins-bot
      - agent-control          # <-- REMOVE THIS
      - file-manager
      - build-manager
```

#### Remove SELF_URL from build-manager environment

Line 35: `SELF_URL: http://build-manager:9010` — remove entirely.
This was only used to construct the webhook callback URL, which no longer exists
after Task 01.

#### Remove AGENT_CONTROL_URL from config-hub environment

Line 60: `AGENT_CONTROL_URL: http://agent-control:9091` — remove from the
base environment. Instead, this will only be set when the agent profile is active.

To set it only with the profile, users will use:
```bash
AGENT_CONTROL_URL=http://agent-control:9091 ./compose.sh --profile agent up -d
```

Or add it to `infra/env/config-hub.env`.

#### Update compose.sh

**File:** `infra/compose.sh`

Document the `--profile agent` flag. Usage examples:

```bash
# Scenario A: own agents (no agent-control)
./compose.sh up -d

# Scenario B: bundled agent
./compose.sh --profile agent up -d

# Mock mode (always includes mock agent-control)
./compose.sh mock up -d
```

### Step 2: Config-hub manager — skip agent scope when unavailable

**File:** `apps/config-hub/src/config_hub/manager.py`

The `_SCOPE_TO_SERVICE` dict (line 33-38) includes `"agent"`. When
agent-control is absent, all iterations over this dict waste time on HTTP
calls that time out.

#### Add a helper property

```python
@property
def _active_scopes(self) -> dict[str, str]:
    """Return only scopes whose service URLs are configured."""
    return {
        scope: svc
        for scope, svc in _SCOPE_TO_SERVICE.items()
        if self.services._service_url(svc) is not None
    }
```

#### Update all iteration loops

Replace `_SCOPE_TO_SERVICE.items()` with `self._active_scopes.items()` in:

1. `fetch_all_schemas()` (line 93-98)
2. `get_config_for_ui()` (line 109-116)
3. `export_env()` (line 151-154)
4. `export_tarball()` (line 179-182)
5. `save_scope()` — keep using `_SCOPE_TO_SERVICE` (line 129) so saving to
   an unconfigured scope gives a proper error, not a silent skip.

#### Handle `export_env()` gracefully

`export_env()` and `export_tarball()` (lines 142-192) explicitly reference
`configs.get("agent", {})` and `schemas.get("agent")`. When agent is absent,
these will be `None`/`{}` which the `generate_env_files()` function should
handle. Verify that `generate_env_files()` doesn't crash on `None` schema.

### Step 3: Config-hub status endpoint — expose agent availability

**File:** The dashboard polls a status endpoint. Add `agent_available` to the
response so the frontend can conditionally render the agent tab.

Find the status route in config-hub's routers (likely `services.py`) and add:

```python
# In the status response:
{
    "services": {
        "bot": {...},
        "agent": {...},
        "file_manager": {...},
        "builds": {...},
    },
    "agent_available": manager.services._agent_url is not None,
}
```

Alternatively, the existing per-service status already returns
`{"available": False, "detail": "service URL not configured"}` when the URL
is None (see `ServiceClient._control()` line 53-59). The frontend can check
the `available` field. Verify this is sufficient or add the explicit flag.

### Step 4: Dashboard — conditional agent tab

**File:** Config-hub dashboard static files (JS/HTML)

When `agent_available` is false (or the agent status returns `available: false`):

1. **Hide or grey out the Agent tab** — don't show a form that can't save
2. **Show informational banner:** "No managed agent — using external agents.
   Agent configuration is not needed for this deployment."
3. **Hide the "Provision Agent" button** (from Task 03) when agent is unavailable

When `agent_available` is true:
- Show the agent config form as usual
- Show the "Provision Agent" button (from Task 03)

### Step 5: Simplify Jenkinsfile template

**File:** `apps/config-hub/src/config_hub/templates/pipeline.groovy`

The current template is 113 lines. The `post` block (lines 59-111) is a 50-line
webhook callback that is entirely eliminated by polling (Task 01).

Replace with a minimal template (~35 lines):

```groovy
// ═══════════════════════════════════════════════════════════════════════════
// Jenkins Flutter Bot — CI/CD Pipeline
// ═══════════════════════════════════════════════════════════════════════════
//
// This pipeline builds a Flutter APK and archives it for download.
// The jenkins-flutter-bot stack polls Jenkins for build completion
// and downloads the archived artifact automatically.
//
// REQUIREMENTS:
//   - BRANCH and BOT_REQUEST_ID parameters (added below)
//   - archiveArtifacts step in the post block
//   - A Jenkins node with Flutter + Android SDKs
//
// If you have an existing pipeline, just add the two parameters and
// the archiveArtifacts line to your existing Jenkinsfile.
// ═══════════════════════════════════════════════════════════════════════════

pipeline {
    agent { label 'flutter' }

    parameters {
        // Branch to build — injected by the bot's /build command
        string(name: 'BRANCH', defaultValue: 'main')

        // Correlation ID — injected automatically by the bot.
        // The pipeline ignores this parameter; it exists solely so the
        // build-manager can match builds to bot requests via the Jenkins API.
        string(name: 'BOT_REQUEST_ID', defaultValue: '')
    }

    stages {
$checkout

        stage('Build APK') {
            steps {
                sh 'flutter pub get'
                sh 'flutter build apk --release'
            }
        }
    }

    post {
        success {
            archiveArtifacts artifacts: 'build/app/outputs/flutter-apk/*.apk'
        }
    }
}
```

**Key changes:**
- Removed `BOT_CALLBACK_URL` and `BOT_JOB_ID` parameters
- Removed the entire 50-line `post { success { script { if (BOT_CALLBACK_URL) ... }}}` block
- Added a simple `archiveArtifacts` in post/success
- Updated comments to explain the polling model
- `$checkout` template substitution remains (for public/private repo variants)

### Step 6: Update `jenkins_pipeline.py` — simplify Jenkinsfile generation

**File:** `apps/config-hub/src/config_hub/jenkins_pipeline.py`

The `generate_jenkinsfile()` function (line 30-51) and `get_jenkinsfile()`
in manager.py (lines 231-263) reference git repo URL and credentials ID
from build-manager config. These are no longer needed since the new template
doesn't include a checkout stage that references credentials.

**Wait** — the `$checkout` substitution is still present. The checkout templates
(`checkout_private.groovy`, `checkout_public.groovy`) handle the git checkout.
These stay as-is. The generator function stays as-is. Only the main
`pipeline.groovy` template changes.

### Step 7: Remove SELF_URL from env example

**File:** `infra/env/build-manager.env.example`

Remove `SELF_URL=` (line 35) from the example env file.

### Step 8: Update mock compose

**File:** `infra/docker-compose.mock.yml`

The mock compose replaces jenkins + agent-control with mock-jenkins.
Verify that mock mode still sets `AGENT_CONTROL_URL` for config-hub
(pointing to the mock agent-control on port 9091). Mock mode should
always simulate the full stack.

## What Stays Unchanged

- All service code (tg-bot, build-manager, file-manager, agent-control)
- Config-hub's `ServiceClient` — already handles `None` URLs gracefully
- `HubBootstrap` — `agent_control_url` is already `str | None = Field(None)`
- Mock agent-control server inside mock-jenkins — unchanged

## Testing Checklist

- [ ] `./compose.sh up -d` (no profile) → 4 services start, no agent-control
- [ ] `./compose.sh --profile agent up -d` → 5 services including agent-control
- [ ] Config-hub dashboard without agent → agent tab hidden/greyed
- [ ] Config-hub dashboard with agent → agent tab visible, config form works
- [ ] `./compose.sh mock up -d` → full stack including mock agent-control
- [ ] Pipeline template generates correct simplified Jenkinsfile
- [ ] Schema/config fetch doesn't time out waiting for absent agent-control
- [ ] `export_env()` and `export_tarball()` work without agent scope

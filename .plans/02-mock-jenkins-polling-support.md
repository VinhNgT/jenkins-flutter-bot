# Task 02: Update Mock Jenkins for Polling

Update the mock-jenkins service to support the polling-based build completion
flow. Currently, mock-jenkins sends a webhook callback after a simulated delay.
After this change, it will instead expose build status and artifact download
endpoints that build-manager polls.

## Why

Task 01 replaces the webhook handler in build-manager with a polling loop.
Mock-jenkins currently simulates the webhook callback (`_send_callback`).
After task 01, build-manager will never receive webhooks — it will poll
Jenkins REST API endpoints. Mock-jenkins needs to expose those endpoints.

## Dependency

**Depends on:** Task 01 (polling-based build completion) being designed, but
can be implemented in parallel — the endpoints are well-defined Jenkins REST API
contracts.

## Scope

**Service:** `mock-jenkins` only.

## Current State

### Key files

| File | Lines | Role |
|------|-------|------|
| `apps/mock-jenkins/src/mock_jenkins/manager.py` | 160 | MockBuildManager — build simulation + webhook callback |
| `apps/mock-jenkins/src/mock_jenkins/routers/jenkins.py` | 214 | Mock Jenkins API routes |
| `apps/mock-jenkins/src/mock_jenkins/config.py` | ~30 | MockJenkinsConfig |

### What mock-jenkins does today

1. `POST /job/{name}/buildWithParameters` — accepts trigger, starts background task
2. Background task sleeps for `MOCK_BUILD_DELAY` seconds
3. Background task POSTs a webhook callback to `BOT_CALLBACK_URL` with a dummy APK
4. `GET /job/{name}/api/json` — returns build history with parameters
5. `POST /queue/cancelItem`, `GET /queue/item/{id}/api/json`, `POST /job/{name}/{num}/stop` — queue/cancel APIs

### What build-manager will poll (from task 01)

1. `GET /queue/item/{queue_id}/api/json` — resolve queue → build number (already exists)
2. `GET /job/{name}/{build_number}/api/json?tree=result,building,...` — build status
3. `GET /job/{name}/{build_number}/api/json?tree=artifacts[relativePath]` — artifact list
4. `GET /job/{name}/{build_number}/artifact/{path}` — artifact download

## Implementation Steps

### Step 1: Remove webhook callback from `manager.py`

**File:** `apps/mock-jenkins/src/mock_jenkins/manager.py`

The `_send_callback()` method (lines 112-159) sends a webhook POST to
`BOT_CALLBACK_URL`. This is no longer needed since build-manager polls
for completion instead.

#### Remove

- `_send_callback()` method entirely
- `httpx` import (only used for webhook callback)
- `callback_url` from `MockBuild` dataclass — no longer needed
- `BOT_CALLBACK_URL` from trigger parameter handling

#### Modify `_simulate_build()`

Instead of calling `_send_callback()`, just update the build's state:

```python
async def _simulate_build(self, build: MockBuild) -> None:
    """Simulate a build by waiting, then marking as complete."""
    try:
        await asyncio.sleep(self.config.mock_build_delay)

        if build.cancelled:
            return

        if self.config.mock_failure_rate > 0 and random.random() < self.config.mock_failure_rate:
            build.result = "FAILURE"
        else:
            build.result = "SUCCESS"

        build.building = False
        build.duration_ms = int((time.time() - build.timestamp) * 1000)
        logger.info("Build #%d completed: %s", build.build_number, build.result)

    except asyncio.CancelledError:
        build.result = "ABORTED"
        build.building = False
        build.duration_ms = int((time.time() - build.timestamp) * 1000)
    except Exception:
        logger.exception("Error simulating build #%d", build.build_number)
        build.result = "FAILURE"
        build.building = False
        build.duration_ms = int((time.time() - build.timestamp) * 1000)
```

#### Update `MockBuild` dataclass

Remove `callback_url` and `job_id` fields (they were webhook-specific).
Add `commit_hash` field (generated on completion):

```python
@dataclass
class MockBuild:
    queue_id: int
    build_number: int
    branch: str
    request_id: str
    building: bool = True
    result: str = ""
    timestamp: float = field(default_factory=time.time)
    duration_ms: int = 0
    cancelled: bool = False
    commit_hash: str = field(default_factory=lambda: uuid.uuid4().hex[:40])
    task: asyncio.Task[None] | None = field(default=None, repr=False)
```

### Step 2: Add per-build status endpoint

**File:** `apps/mock-jenkins/src/mock_jenkins/routers/jenkins.py`

Build-manager polls `GET /job/{name}/{build_number}/api/json?tree=...` to check
if a build is done. Add this route:

```python
@router.get("/job/{job_name}/{build_number}/api/json")
async def build_api(
    manager: ManagerDep, job_name: str, build_number: int, tree: str = ""
) -> dict[str, Any] | Response:
    """Return individual build info — status, result, actions."""
    build = manager.builds.get(build_number)
    if build is None:
        return Response(status_code=404)

    # Simulate Git plugin's lastBuiltRevision in actions
    actions: list[dict[str, Any]] = [
        {
            "parameters": [
                {"name": "BRANCH", "value": build.branch},
                {"name": "BOT_REQUEST_ID", "value": build.request_id},
            ]
        },
    ]

    # Add lastBuiltRevision when build is complete (simulates Git plugin)
    if not build.building:
        actions.append({
            "lastBuiltRevision": {"SHA1": build.commit_hash},
        })

    result: dict[str, Any] = {
        "_class": "org.jenkinsci.plugins.workflow.job.WorkflowRun",
        "number": build.build_number,
        "result": build.result if not build.building else None,
        "building": build.building,
        "timestamp": int(build.timestamp * 1000),
        "duration": build.duration_ms,
        "actions": actions,
    }

    # Artifacts only present when build succeeded
    if build.result == "SUCCESS":
        result["artifacts"] = [
            {"relativePath": "build/app/outputs/flutter-apk/app-release.apk"}
        ]
    else:
        result["artifacts"] = []

    return result
```

### Step 3: Add artifact download endpoint

**File:** `apps/mock-jenkins/src/mock_jenkins/routers/jenkins.py`

Build-manager downloads artifacts via `GET /job/{name}/{build}/artifact/{path}`.

```python
@router.get("/job/{job_name}/{build_number}/artifact/{artifact_path:path}")
async def download_artifact(
    manager: ManagerDep,
    job_name: str,
    build_number: int,
    artifact_path: str,
) -> Response:
    """Serve a dummy APK artifact for download."""
    build = manager.builds.get(build_number)
    if build is None or build.result != "SUCCESS":
        return Response(status_code=404)

    return Response(
        content=DUMMY_APK,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="app-release.apk"'
        },
    )
```

Import `DUMMY_APK` from `..manager` at the top of the file.

### Step 4: Update trigger endpoint — remove webhook params

**File:** `apps/mock-jenkins/src/mock_jenkins/routers/jenkins.py`

The `trigger_build` route (line 88-129) currently accepts `BOT_CALLBACK_URL`
and `BOT_JOB_ID` query parameters. Remove them:

```python
# Before:
@router.post("/job/{job_name}/buildWithParameters")
async def trigger_build(
    ...,
    BRANCH: str = Query(default="main"),
    BOT_CALLBACK_URL: str = Query(default=""),
    BOT_REQUEST_ID: str = Query(default=""),
    BOT_JOB_ID: str = Query(default=""),
) -> Response:

# After:
@router.post("/job/{job_name}/buildWithParameters")
async def trigger_build(
    ...,
    BRANCH: str = Query(default="main"),
    BOT_REQUEST_ID: str = Query(default=""),
) -> Response:
```

Update the `MockBuild` construction to match the new dataclass.

### Step 5: Update build history endpoint — remove webhook params

**File:** `apps/mock-jenkins/src/mock_jenkins/routers/jenkins.py`

In `job_api()` (line 38-80), update the `actions.parameters` to only include
`BRANCH` and `BOT_REQUEST_ID` (remove `BOT_CALLBACK_URL` and `BOT_JOB_ID`).

### Step 6: Add CSRF crumb endpoint (needed for task 03)

Build-manager (in task 03) will need a CSRF crumb for POST requests when
creating Jenkins nodes. Add it now since it's a simple mock:

```python
@router.get("/crumbIssuer/api/json")
async def crumb_issuer() -> dict[str, str]:
    """Return a mock CSRF crumb — always accepted by the mock."""
    return {
        "crumb": "mock-crumb-token",
        "crumbRequestField": "Jenkins-Crumb",
    }
```

### Step 7: Update `main.py` docstring

**File:** `apps/mock-jenkins/src/mock_jenkins/main.py`

Update the module docstring (lines 1-6) to reflect polling instead of webhook:

```python
"""Mock Jenkins server — FastAPI app factory and CLI.

Simulates the Jenkins REST API for local development.
On trigger, spawns a background task that waits MOCK_BUILD_DELAY seconds,
then marks the build as complete. Build-manager polls for completion via
the standard Jenkins REST API endpoints.
"""
```

## What Stays Unchanged

- Queue management endpoints (cancelItem, queue item info, stop build)
- `MockJenkinsConfig` — same config fields
- Mock agent-control server (runs on port 9091) — unaffected
- Build delay and failure rate simulation — same behavior

## Testing Checklist

- [ ] Trigger build → verify build starts, `building=True` initially
- [ ] Wait for delay → verify `building=False`, `result` set
- [ ] Poll per-build status → verify response matches expected schema
- [ ] Download artifact → verify dummy APK content returned
- [ ] Failed build → verify no artifacts in artifact list
- [ ] Cancelled build → verify `result="ABORTED"`
- [ ] CSRF crumb endpoint returns valid response

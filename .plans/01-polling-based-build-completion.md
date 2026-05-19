# Task 01: Polling-Based Build Completion

Replace the webhook-driven build completion mechanism with a polling loop
that tracks build status via the Jenkins REST API.

## Why

The current system requires a 100-line Groovy `post` block in the Jenkinsfile
that `curl`s a multipart webhook back to build-manager. This is fragile,
hard to debug, and forces users to use our exact Jenkinsfile template.

Polling eliminates the webhook entirely — build-manager monitors Jenkins via
its existing REST API, downloads the artifact when done, and notifies the
frontend. The user's Jenkinsfile only needs `archiveArtifacts`.

## Scope

**Service:** `build-manager` only.
**No changes to:** config-hub, mock-jenkins, tg-bot, docker-compose (those are separate tasks).

## Current State

### Build lifecycle (what we're replacing)

```
1. bot → build-manager: POST /api/builds/trigger
2. build-manager → jenkins: POST /job/{name}/buildWithParameters
                            params: BRANCH, BOT_CALLBACK_URL, BOT_REQUEST_ID, BOT_JOB_ID
3. jenkins agent: runs flutter build apk
4. jenkins pipeline (post block): curl -X POST {BOT_CALLBACK_URL}
                                  -F 'metadata={...json...}'
                                  -F 'artifact=@app-release.apk'
5. build-manager: receives multipart POST at /api/builds/webhook
                  uploads artifact to file-manager, notifies bot
```

### Key files

| File | Lines | Current role |
|------|-------|-------------|
| `apps/build-manager/src/build_manager/builds/jenkins_client.py` | 257 | Jenkins REST API client — trigger, query, cancel |
| `apps/build-manager/src/build_manager/builds/coordinator.py` | 373 | Orchestrates builds — trigger, webhook handler, timeout, upload, eviction |
| `apps/build-manager/src/build_manager/builds/state.py` | 230 | PendingBuild/CompletedBuild dataclasses, BuildTracker persistence |
| `apps/build-manager/src/build_manager/config.py` | 108 | BuildSettings — Jenkins creds, self_url, timeouts |
| `apps/build-manager/src/build_manager/manager.py` | 104 | BuildManager — lifecycle, creates coordinator |
| `apps/build-manager/src/build_manager/routers/builds.py` | 140 | API routes — trigger, webhook, pending, recent, cancel |

## Target State

```
1. bot → build-manager: POST /api/builds/trigger (unchanged)
2. build-manager → jenkins: POST /job/{name}/buildWithParameters
                            params: BRANCH, BOT_REQUEST_ID (only 2 params)
3. build-manager: starts polling loop for this build
4. build-manager: polls GET /job/{name}/api/json until build completes
5. build-manager: downloads artifact via GET /job/{name}/{build}/artifact/...
6. build-manager → file-manager: uploads artifact (unchanged)
7. build-manager → bot: frontend callback (unchanged)
```

## Implementation Steps

### Step 1: Add polling methods to `JenkinsClient`

**File:** `apps/build-manager/src/build_manager/builds/jenkins_client.py`

Add three new methods:

#### `resolve_build_number(queue_id) -> int | None`

Polls `GET /queue/item/{queue_id}/api/json` to resolve queue ID → build number.
Returns `executable.number` when the build starts, `None` if still queued.

This is needed because Jenkins doesn't assign a build number until the build
actually starts (it might sit in the queue waiting for an executor).

```python
async def resolve_build_number(self, queue_id: int) -> int | None:
    """Resolve a queue item to its build number.

    Returns None if the build hasn't started yet (still queued).
    """
    url = f"{self.base_url}/queue/item/{queue_id}/api/json"
    resp = await self._client.get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    executable = data.get("executable")
    if executable and "number" in executable:
        return executable["number"]
    return None
```

#### `get_build_status(build_number) -> dict`

Fetches a single build's status: result, building flag, and actions (for commit hash).

The commit hash is available from the Jenkins Git plugin as `lastBuiltRevision`
inside the build's `actions` array. We no longer need the Groovy `git rev-parse`.

```python
async def get_build_status(self, build_number: int) -> dict[str, Any]:
    """Fetch the status of a specific build.

    Returns dict with keys: result, building, commit_hash.
    """
    tree = "result,building,actions[lastBuiltRevision[SHA1]]"
    url = f"{self.job_url}/{build_number}/api/json?tree={tree}"
    resp = await self._client.get(url)
    resp.raise_for_status()
    data = resp.json()

    commit_hash = ""
    for action in data.get("actions", []):
        rev = action.get("lastBuiltRevision", {})
        if "SHA1" in rev:
            commit_hash = rev["SHA1"]
            break

    return {
        "result": data.get("result") or "",
        "building": data.get("building", False),
        "commit_hash": commit_hash,
    }
```

#### `download_artifact(build_number, pattern) -> tuple[str, bytes] | None`

Lists artifacts via `GET /job/{name}/{build}/api/json?tree=artifacts[relativePath]`
and downloads the first matching file. Returns `(filename, content_bytes)` or `None`.

```python
async def download_artifact(
    self, build_number: int, pattern: str = "*.apk"
) -> tuple[str, bytes] | None:
    """Download the first artifact matching the glob pattern.

    Returns (filename, bytes) or None if no matching artifact found.
    """
    import fnmatch

    list_url = f"{self.job_url}/{build_number}/api/json?tree=artifacts[relativePath]"
    resp = await self._client.get(list_url)
    resp.raise_for_status()

    artifacts = resp.json().get("artifacts", [])
    match = None
    for art in artifacts:
        rel_path = art.get("relativePath", "")
        if fnmatch.fnmatch(rel_path.split("/")[-1], pattern):
            match = rel_path
            break

    if match is None:
        return None

    dl_url = f"{self.job_url}/{build_number}/artifact/{match}"
    resp = await self._client.get(dl_url)
    resp.raise_for_status()
    filename = match.split("/")[-1]
    return filename, resp.content
```

#### Modify `trigger_build()` signature

Remove `callback_url` and `job_id` parameters. Only send `BRANCH` + `BOT_REQUEST_ID`.

**Before:**
```python
async def trigger_build(self, branch, callback_url, request_id, job_id) -> int:
    params = {"BRANCH": branch, "BOT_CALLBACK_URL": callback_url,
              "BOT_REQUEST_ID": request_id, "BOT_JOB_ID": job_id}
```

**After:**
```python
async def trigger_build(self, branch: str, request_id: str) -> int:
    params = {"BRANCH": branch, "BOT_REQUEST_ID": request_id}
```

#### Update comment in `get_builds()`

Line 105-107 currently says: `# commit_hash comes from webhook metadata, not Jenkins`.
Update to: `# commit_hash is populated by the polling loop from Jenkins build API`.

Also update the `commit_hash` extraction to use `lastBuiltRevision` from actions
(same logic as `get_build_status`). The current code always sets it to `""`.

### Step 2: Refactor `BuildCoordinator` — replace webhook with polling

**File:** `apps/build-manager/src/build_manager/builds/coordinator.py`

#### Remove

- `webhook_url` property (line 75-78) — no longer needed
- `self_url` constructor parameter and `_self_url` field (line 48, 54)
- `handle_webhook()` method (lines 214-275) — entire method
- `_timeout_worker()` method (lines 165-174) — replaced by polling worker
- `_handle_timeout()` method (lines 176-208) — absorbed into polling worker

#### Add constants

```python
POLL_INTERVAL = 10          # seconds between polls (overridden by config)
QUEUE_RESOLVE_TIMEOUT = 60  # max seconds to wait for queue → build number
```

#### Replace `_start_timeout_task` → `_start_polling_task`

```python
def _start_polling_task(self, request_id: str, queue_id: int) -> None:
    """Spawn a polling task that tracks this build to completion."""
    task = asyncio.create_task(
        self._polling_worker(request_id, queue_id)
    )
    self._polling_tasks[request_id] = task
```

#### Add `_polling_worker()` — the core new method

This is the main logic that replaces both the webhook handler and the timeout task.

```python
async def _polling_worker(self, request_id: str, queue_id: int) -> None:
    """Poll Jenkins until the build completes or times out.

    Phases:
    1. Queue resolution — poll queue API until build number assigned
    2. Build monitoring — poll build API until building=False
    3. Completion — download artifact, upload, notify frontend
    """
    try:
        # Phase 1: resolve queue_id → build_number
        build_number = await self._resolve_build_number(request_id, queue_id)
        if build_number is None:
            return  # timed out or cancelled, _resolve_build_number handled it

        # Phase 2: poll until build completes
        result = await self._poll_build(request_id, build_number)
        if result is None:
            return  # timed out or cancelled

        # Phase 3: handle completion
        await self._handle_build_result(request_id, build_number, result)

    except asyncio.CancelledError:
        return  # Build was cancelled
    except Exception:
        logger.exception("Polling worker failed for %s", request_id)
        # Treat as timeout — notify frontend of failure
        await self._handle_timeout(request_id)
    finally:
        self._polling_tasks.pop(request_id, None)
```

#### Add `_resolve_build_number()`

```python
async def _resolve_build_number(
    self, request_id: str, queue_id: int
) -> int | None:
    """Poll the Jenkins queue until the build number is assigned."""
    deadline = time.time() + QUEUE_RESOLVE_TIMEOUT
    while time.time() < deadline:
        build_number = await self._jenkins.resolve_build_number(queue_id)
        if build_number is not None:
            logger.info(
                "Queue %d resolved to build #%d for %s",
                queue_id, build_number, request_id,
            )
            return build_number
        await asyncio.sleep(2)  # faster polling for queue resolution

    logger.warning("Queue resolution timed out for %s (queue_id=%d)",
                   request_id, queue_id)
    await self._handle_timeout(request_id)
    return None
```

#### Add `_poll_build()`

```python
async def _poll_build(
    self, request_id: str, build_number: int
) -> dict[str, Any] | None:
    """Poll until the build finishes or the timeout expires."""
    timeout_seconds = self._build_timeout * 60
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        status = await self._jenkins.get_build_status(build_number)
        if not status["building"]:
            return status
        await asyncio.sleep(self._poll_interval)

    logger.warning("Build timed out: %s (build #%d)", request_id, build_number)
    await self._handle_timeout(request_id)
    return None
```

#### Add `_handle_build_result()`

This replaces the body of `handle_webhook()`. Downloads artifact, uploads, notifies.

```python
async def _handle_build_result(
    self, request_id: str, build_number: int, status: dict[str, Any]
) -> None:
    """Process a completed build — download, upload, notify."""
    pending = self._tracker.consume_pending(request_id)
    if pending is None:
        return

    jenkins_result = status.get("result", "")
    # Jenkins uses uppercase (SUCCESS/FAILURE), we use lowercase
    build_status = "success" if jenkins_result == "SUCCESS" else "failure"
    commit_hash = status.get("commit_hash", "")
    now = time.time()

    download_url = ""
    file_id = ""

    if build_status == "success":
        try:
            artifact = await self._jenkins.download_artifact(
                build_number, self._artifact_pattern
            )
            if artifact:
                original_name, content = artifact
                # Build a descriptive filename:
                # {job_name}_{branch}_{YYYYMMDD_HHmmss}.apk
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(now, tz=timezone.utc)
                suffix = Path(original_name).suffix  # .apk
                upload_name = (
                    f"{self._jenkins.job_name}_{pending.branch}"
                    f"_{dt.strftime('%Y%m%d_%H%M%S')}{suffix}"
                )
                upload_result = await self._upload_artifact(upload_name, content)
                download_url = upload_result.get("download_url", "")
                file_id = upload_result.get("file_id", "")
        except Exception:
            logger.exception("Artifact download/upload failed for %s", request_id)

    completed, evicted = self._tracker.record_completed(
        request_id,
        branch=pending.branch,
        commit_hash=commit_hash,
        result=build_status,
        triggered_at=pending.triggered_at,
        completed_at=now,
        download_url=download_url,
        file_id=file_id,
    )

    await self._evict_builds(evicted)

    if pending.frontend_callback_url:
        await self._notify_frontend(pending.frontend_callback_url, completed)
```

#### Modify `_upload_artifact()`

**Before** (line 277-287): reads from a filesystem path (temp file from webhook upload).

**After:** accepts `(filename: str, content: bytes)` — content comes from Jenkins download.

```python
async def _upload_artifact(self, filename: str, content: bytes) -> dict[str, Any]:
    """Upload a build artifact to the file-manager service."""
    url = f"{self._file_manager_url}/api/files/upload"
    resp = await self._http.post(
        url,
        files={"file": (filename, content)},
    )
    resp.raise_for_status()
    return resp.json()
```

#### Modify `__init__` signature

- Remove `self_url` parameter
- Add `poll_interval` parameter (default 10)
- Add `artifact_pattern` parameter (default `"*.apk"`)
- Rename `_timeout_tasks` → `_polling_tasks`

```python
def __init__(
    self,
    *,
    data_dir: Path,
    file_manager_url: str,
    max_recent_builds: int = 3,
    build_timeout: int = 30,
    poll_interval: int = 10,
    artifact_pattern: str = "*.apk",
) -> None:
```

#### Modify `trigger_build()`

```python
# Before (line 122-127):
queue_id = await self._jenkins.trigger_build(
    branch=branch,
    callback_url=self.webhook_url,
    request_id=request_id,
    job_id=job_id,
)

# After:
queue_id = await self._jenkins.trigger_build(
    branch=branch,
    request_id=request_id,
)
```

Replace `self._start_timeout_task(request_id)` with
`self._start_polling_task(request_id, queue_id)`.

Remove `job_id = request_id` (line 120) — job_id is no longer used.

#### Modify `cancel_build()`

Rename `_cancel_timeout_task` → `_cancel_polling_task`.
The rest of the cancel logic is unchanged.

#### Modify `close()`

Rename `_timeout_tasks` → `_polling_tasks` in the cleanup loop.

#### Keep `_handle_timeout()` (lines 176-208)

Keep this method mostly as-is — it's still needed for polling timeouts.
Only rename the internal reference from `_cancel_timeout_task` if called.

### Step 3: Update `config.py` — add polling config, remove self_url

**File:** `apps/build-manager/src/build_manager/config.py`

#### Remove

`self_url` field (lines 71-79). This was only needed to construct the webhook URL.

#### Add

```python
poll_interval: int = Field(
    10,
    title="Poll Interval (seconds)",
    description="How often to check Jenkins for build completion",
    json_schema_extra={
        "group": "Advanced",
        "json_key": "builds.poll_interval",
    },
)
artifact_pattern: str = Field(
    "*.apk",
    title="Artifact Pattern",
    description="Glob pattern to match build artifacts in the Jenkins archive",
    json_schema_extra={
        "group": "Advanced",
        "help_html": (
            "Pattern to find the build artifact. Default "
            "<code>*.apk</code> matches any APK. Change to "
            "<code>*.aab</code> for app bundles."
        ),
        "json_key": "builds.artifact_pattern",
    },
)
```

### Step 4: Update `manager.py` — remove self_url, add new config fields

**File:** `apps/build-manager/src/build_manager/manager.py`

In `start()` method (line 49-55), update the `BuildCoordinator` constructor:

```python
# Before:
coord = BuildCoordinator(
    data_dir=config.build_data_path,
    self_url=config.self_url,
    file_manager_url=config.file_manager_url,
    max_recent_builds=config.max_recent_builds,
    build_timeout=config.build_timeout,
)

# After:
coord = BuildCoordinator(
    data_dir=config.build_data_path,
    file_manager_url=config.file_manager_url,
    max_recent_builds=config.max_recent_builds,
    build_timeout=config.build_timeout,
    poll_interval=config.poll_interval,
    artifact_pattern=config.artifact_pattern,
)
```

### Step 5: Remove webhook route from `routers/builds.py`

**File:** `apps/build-manager/src/build_manager/routers/builds.py`

Delete the entire `build_webhook` function (lines 51-89) and its imports
(`json`, `os`, `tempfile`, `UploadFile`).

Update the module docstring to remove the webhook endpoint reference.

### Step 6: Update `coordinator.py` class docstring

Replace the flow description to reflect polling instead of webhook:

```python
"""Coordinates the full build lifecycle.

Flow:
    1. Frontend calls ``trigger_build(branch, callback_url)``
    2. Coordinator triggers Jenkins and registers a ``PendingBuild``
    3. Polling task starts: queue resolution → build monitoring
    4. On build completion: download artifact from Jenkins archive
    5. Upload artifact to file-manager, enforce retention
    6. Forward result to the frontend callback URL
"""
```

## What Stays Unchanged

- `BuildTracker` (`state.py`) — no changes at all
- `PendingBuild` / `CompletedBuild` dataclasses — no changes
- `cancel_build()` — same logic (cancel the task, cancel in Jenkins)
- `_evict_builds()` — unchanged
- `_notify_frontend()` — unchanged (same payload shape)
- `record_completed()` call shape — same fields
- File-manager upload API — same endpoint
- Bot callback flow — same payload

## Testing Checklist

- [ ] Trigger build → verify polling task starts and polls at `poll_interval`
- [ ] Build completes → verify artifact downloaded + uploaded to file-manager
- [ ] Build fails → verify frontend notified with `result: "failure"`, no artifact
- [ ] Build times out → verify timeout handling fires, frontend notified
- [ ] Cancel pending build → verify polling task cancelled, Jenkins build stopped
- [ ] Uploaded filename follows `{job}_{branch}_{datetime}.apk` format
- [ ] Queue resolution → verify queue_id → build_number mapping works
- [ ] Jenkins unreachable during poll → verify error handling

## Open Questions

1. **`self_url` removal** — Verify nothing else reads `self_url` from
   `BuildSettings`. Search the codebase for `self_url` before removing.

2. **Artifact pattern matching** — `fnmatch` matches basenames. Confirm this
   handles Jenkins artifact relative paths correctly (e.g., does
   `build/app/outputs/flutter-apk/app-release.apk` match `*.apk` when we
   only match the last path component?).

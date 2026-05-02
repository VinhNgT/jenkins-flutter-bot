"""HTTP control wrapper for a Jenkins inbound agent process."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@dataclass(frozen=True)
class AgentConfig:
    jenkins_url: str
    agent_name: str
    secret: str
    web_socket: bool
    tunnel: str

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> AgentConfig:
        load_dotenv()

        resolved_path = config_path
        if resolved_path is None and os.environ.get("CONFIG_PATH"):
            resolved_path = Path(os.environ["CONFIG_PATH"])

        file_data: dict[str, Any] = {}
        if resolved_path and resolved_path.exists():
            file_data = json.loads(resolved_path.read_text())

        def get_value(
            file_key: str,
            env_key: str,
            *,
            default: str = "",
            required: bool = False,
        ) -> str:
            file_value = _nested_get(file_data, file_key)
            if file_value not in (None, ""):
                return str(file_value)

            env_value = os.environ.get(env_key)
            if env_value not in (None, ""):
                return env_value

            if required and default == "":
                raise KeyError(env_key)

            return default

        web_socket_raw = get_value(
            "agent.web_socket",
            "JENKINS_WEB_SOCKET",
            default="true",
        )

        return cls(
            jenkins_url=get_value(
                "jenkins.url",
                "JENKINS_URL",
                default="http://jenkins:8080",
            ),
            agent_name=get_value(
                "agent.name",
                "JENKINS_AGENT_NAME",
                default="flutter-agent",
            ),
            secret=get_value(
                "agent.secret",
                "JENKINS_SECRET",
                required=True,
            ),
            web_socket=web_socket_raw.lower() not in {"0", "false", "no"},
            tunnel=get_value(
                "agent.tunnel",
                "JENKINS_TUNNEL",
                default="",
            ),
        )


class AgentManager:
    """Manage the Jenkins inbound agent subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._last_error: str | None = None
        self._config: AgentConfig | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, config: AgentConfig) -> None:
        if self.running:
            return

        command = [
            "/usr/local/bin/jenkins-agent",
            "-url",
            config.jenkins_url,
            "-secret",
            config.secret,
            "-name",
            config.agent_name,
        ]
        if config.web_socket:
            command.append("-webSocket")
        if config.tunnel:
            command.extend(["-tunnel", config.tunnel])

        logger.info("Starting Jenkins agent: %s", command)
        try:
            self._process = subprocess.Popen(command, text=True)
            self._config = config
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("Failed to start Jenkins agent")
            raise

    def stop(self) -> None:
        if not self._process:
            return

        logger.info("Stopping Jenkins agent...")
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        finally:
            self._process = None
            self._config = None

    def status(self) -> dict[str, Any]:
        return {
            "configured": self._config is not None,
            "running": self.running,
            "pid": self._process.pid if self.running and self._process else None,
            "last_error": self._last_error,
            "agent_name": self._config.agent_name if self._config else None,
        }


from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def lifespan(app: FastAPI) -> Generator[None, None, None]:
    """Manage agent lifecycle on startup/shutdown."""
    try:
        config = AgentConfig.resolve()
        app.state.manager.start(config)
    except Exception as exc:
        logger.info("Agent not auto-started: %s", exc)

    yield

    app.state.manager.stop()


app = FastAPI(title="agent-control", lifespan=lifespan)
app.state.manager = AgentManager()


@app.post("/control/start")
async def start() -> dict[str, Any]:
    try:
        config = AgentConfig.resolve()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    app.state.manager.start(config)
    return app.state.manager.status()


@app.post("/control/stop")
async def stop() -> dict[str, Any]:
    app.state.manager.stop()
    return app.state.manager.status()


@app.post("/control/restart")
async def restart() -> dict[str, Any]:
    try:
        config = AgentConfig.resolve()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    app.state.manager.stop()
    app.state.manager.start(config)
    return app.state.manager.status()


@app.get("/control/status")
async def status() -> dict[str, Any]:
    return app.state.manager.status()

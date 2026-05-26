import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

from config_core.schema import resolve_config_path

logger = logging.getLogger(__name__)


class VpnManager:
    """Manage an OpenVPN client subprocess.

    The .ovpn config is a single-seat connection shared with another machine.
    Only one client can be connected at a time — connecting here disconnects
    the other user. Build-manager orchestrates connect/disconnect to keep
    the window as short as possible (active builds only).

    OpenVPN is run as a managed child process (no ``--daemon`` flag).
    This avoids zombie processes in Docker containers where PID 1 does not
    reap orphaned children, and gives us direct ``terminate()``/``kill()``
    control with reliable ``wait()``-based exit detection.

    A safety timer auto-disconnects the VPN after a configurable maximum
    duration, preventing orphaned sessions when build-manager crashes or
    fails to issue a disconnect.
    """

    def __init__(self) -> None:
        self._auto_disconnect_task: asyncio.Task[None] | None = None
        self._max_connected_minutes: int = 0
        self._process: asyncio.subprocess.Process | None = None

    @property
    def OVPN_PATH(self) -> Path:
        return resolve_config_path(Path("/app/data/client.ovpn"))

    @property
    def PID_PATH(self) -> Path:
        # Resolved alongside OVPN_PATH so both redirect to tmp_path during tests,
        # preventing PID file writes to the real /tmp and conflicts with host
        # OpenVPN processes.
        return resolve_config_path(Path("/app/data/.openvpn.pid"))

    @property
    def LOG_PATH(self) -> Path:
        # Log path for OpenVPN output, useful for troubleshooting handshakes
        # and network routing issues. Redirected under JFB_DATA_DIR in tests.
        return resolve_config_path(Path("/app/data/openvpn.log"))

    @property
    def connected(self) -> bool:
        """Check if the OpenVPN process is alive and tun interface exists."""
        if self._process is None or self._process.returncode is not None:
            return False

        # Check if tun interface is present in /sys/class/net
        net_dir = Path("/sys/class/net")
        if net_dir.exists():
            has_tun = any(p.name.startswith("tun") for p in net_dir.iterdir())
            if not has_tun:
                return False

        return True

    def set_max_connected_minutes(self, minutes: int) -> None:
        """Configure the auto-disconnect safety timer duration."""
        self._max_connected_minutes = minutes

    async def connect(self) -> None:
        """Start the OpenVPN client. Blocks until tun interface is up or timeout (30s)."""
        if self.connected:
            logger.info("VPN is already connected.")
            self._start_safety_timer()
            return

        if not self.OVPN_PATH.exists():
            raise FileNotFoundError(f"OpenVPN config not found at {self.OVPN_PATH}")

        logger.info("Starting OpenVPN tunnel...")

        # Kill any lingering process from a previous run
        await self._kill_existing()

        # Run openvpn as a managed child (no --daemon). stdout/stderr go to
        # the log file; the process stays attached so we can terminate() it
        # and wait() for clean exit detection.
        cmd = [
            "openvpn",
            "--config",
            str(self.OVPN_PATH),
            "--writepid",
            str(self.PID_PATH),
            "--log",
            str(self.LOG_PATH),
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("openvpn executable not found. Make sure it is installed.")
            raise RuntimeError("openvpn executable not found on the system.")

        # Wait for tun interface to come up
        timeout = 30.0
        poll_interval = 0.5
        elapsed = 0.0

        while elapsed < timeout:
            # Check if process died early (bad config, auth failure, etc.)
            if self._process.returncode is not None:
                err_msg = ""
                if self.LOG_PATH.exists():
                    err_msg = self.LOG_PATH.read_text().strip().splitlines()[-1]
                raise RuntimeError(f"OpenVPN exited with code {self._process.returncode}: {err_msg}")

            if self.connected:
                logger.info("VPN connected successfully (tun interface up).")
                self._start_safety_timer()
                return
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout reached, clean up
        logger.error("Timeout waiting for VPN tun interface to come up.")
        await self.disconnect()
        raise TimeoutError("Timeout waiting for VPN connection to establish.")

    async def disconnect(self) -> None:
        """Terminate the OpenVPN process and wait for it to exit."""
        self._cancel_safety_timer()

        if self._process is None or self._process.returncode is not None:
            logger.info("VPN is not connected (no running process).")
            self._cleanup_pid_file()
            return

        pid = self._process.pid
        logger.info("Disconnecting VPN (PID %d)...", pid)

        # SIGTERM for graceful shutdown
        try:
            self._process.terminate()
        except ProcessLookupError:
            logger.info("OpenVPN process already exited.")
            self._cleanup_pid_file()
            return

        # Wait for exit with timeout. Since we hold the Process object,
        # wait() detects exit reliably (no zombie issue).
        try:
            await asyncio.wait_for(self._process.wait(), timeout=10.0)
            logger.info("OpenVPN process stopped gracefully.")
        except asyncio.TimeoutError:
            logger.warning(
                "OpenVPN process (PID %d) did not stop after 10s. Sending SIGKILL...",
                pid,
            )
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass

        self._cleanup_pid_file()
        logger.info("VPN disconnected.")

    async def _kill_existing(self) -> None:
        """Kill any lingering OpenVPN process from a previous run."""
        # Kill managed process if still alive
        if self._process is not None and self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
            self._process = None

        # Also clean up stale PID file from a --daemon-era process or crash
        if self.PID_PATH.exists():
            try:
                pid = int(self.PID_PATH.read_text().strip())
                logger.info("Killing old lingering OpenVPN process (PID %d)...", pid)
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
            self._cleanup_pid_file()

    def _cleanup_pid_file(self) -> None:
        """Remove the PID file if it exists."""
        try:
            self.PID_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    def status(self) -> dict[str, Any]:
        """Return VPN connection status for the control API."""
        uploaded = self.OVPN_PATH.exists()
        size = self.OVPN_PATH.stat().st_size if uploaded else 0
        return {
            "uploaded": uploaded,
            "size": size,
            "connected": self.connected,
        }

    # ------------------------------------------------------------------
    # Safety timer
    # ------------------------------------------------------------------

    def _start_safety_timer(self) -> None:
        """Start (or restart) the auto-disconnect timer."""
        self._cancel_safety_timer()
        if self._max_connected_minutes <= 0:
            return
        self._auto_disconnect_task = asyncio.create_task(
            self._safety_timer_worker(self._max_connected_minutes)
        )

    def _cancel_safety_timer(self) -> None:
        """Cancel any running auto-disconnect timer."""
        if self._auto_disconnect_task is not None:
            self._auto_disconnect_task.cancel()
            self._auto_disconnect_task = None

    async def _safety_timer_worker(self, minutes: int) -> None:
        """Sleep for the configured duration, then force-disconnect."""
        try:
            await asyncio.sleep(minutes * 60)
            logger.warning(
                "VPN auto-disconnected after %d minutes (safety limit reached)",
                minutes,
            )
            await self.disconnect()
        except asyncio.CancelledError:
            pass  # Timer cancelled by explicit disconnect — expected

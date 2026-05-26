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

    A safety timer auto-disconnects the VPN after a configurable maximum
    duration, preventing orphaned sessions when build-manager crashes or
    fails to issue a disconnect.
    """

    def __init__(self) -> None:
        self._auto_disconnect_task: asyncio.Task[None] | None = None
        self._max_connected_minutes: int = 0

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
        if not self.PID_PATH.exists():
            return False

        try:
            pid = int(self.PID_PATH.read_text().strip())
        except (ValueError, OSError):
            return False

        # Check if process is running (send signal 0)
        try:
            os.kill(pid, 0)
        except OSError:
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

        # Clear old process and PID if any
        if self.PID_PATH.exists():
            try:
                pid = int(self.PID_PATH.read_text().strip())
                logger.info(f"Killing old lingering OpenVPN process (PID {pid}) prior to connection...")
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
            try:
                self.PID_PATH.unlink()
            except OSError:
                pass

        # Spawns: openvpn --config /app/data/client.ovpn --daemon --writepid /tmp/openvpn.pid --log /app/data/openvpn.log
        cmd = [
            "openvpn",
            "--config",
            str(self.OVPN_PATH),
            "--daemon",
            "--writepid",
            str(self.PID_PATH),
            "--log",
            str(self.LOG_PATH),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError:
            logger.error("openvpn executable not found. Make sure it is installed.")
            raise RuntimeError("openvpn executable not found on the system.")

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error(f"Failed to start OpenVPN process: {err_msg}")
            raise RuntimeError(f"OpenVPN failed to start: {err_msg}")

        # Wait for PID file and tun interface
        timeout = 30.0
        poll_interval = 0.5
        elapsed = 0.0

        while elapsed < timeout:
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
        """Send SIGTERM to the OpenVPN process, wait 5s, then SIGKILL."""
        self._cancel_safety_timer()

        if not self.PID_PATH.exists():
            logger.info("VPN is not connected (no PID file).")
            return

        try:
            pid = int(self.PID_PATH.read_text().strip())
        except (ValueError, OSError) as e:
            logger.warning(f"Could not read OpenVPN PID: {e}")
            # Remove PID file to clear state
            try:
                self.PID_PATH.unlink()
            except OSError:
                pass
            return

        logger.info(f"Disconnecting VPN (PID {pid})...")

        # Try SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            logger.warning(f"Failed to send SIGTERM to OpenVPN (PID {pid}): {e}")
            # Process might already be dead
            try:
                self.PID_PATH.unlink()
            except OSError:
                pass
            return

        # Wait up to 5s for process to exit
        timeout = 5.0
        poll_interval = 0.2
        elapsed = 0.0
        while elapsed < timeout:
            try:
                os.kill(pid, 0)
            except OSError:
                # Process is dead!
                logger.info("OpenVPN process stopped.")
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        else:
            # Still alive, SIGKILL
            logger.warning(f"OpenVPN process (PID {pid}) did not stop after 5s. Sending SIGKILL...")
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError as e:
                logger.warning(f"Failed to send SIGKILL to OpenVPN: {e}")

        # Clean up PID file
        if self.PID_PATH.exists():
            try:
                self.PID_PATH.unlink()
            except OSError:
                pass

        logger.info("VPN disconnected.")

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

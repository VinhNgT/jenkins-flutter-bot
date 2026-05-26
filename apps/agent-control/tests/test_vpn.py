import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from agent_control.vpn import VpnManager


@pytest.mark.asyncio
async def test_vpn_manager_connect_missing_file():
    vpn = VpnManager()
    if vpn.OVPN_PATH.exists():
        vpn.OVPN_PATH.unlink()

    with pytest.raises(FileNotFoundError):
        await vpn.connect()


@pytest.mark.asyncio
async def test_vpn_manager_connect_already_connected():
    vpn = VpnManager()

    with patch.object(VpnManager, "connected", new_callable=PropertyMock, return_value=True):
        await vpn.connect()  # Should return early without spawning openvpn


@pytest.mark.asyncio
async def test_vpn_manager_connect_success():
    vpn = VpnManager()
    vpn.OVPN_PATH.parent.mkdir(parents=True, exist_ok=True)
    vpn.OVPN_PATH.write_text("client-config")

    if vpn.PID_PATH.exists():
        vpn.PID_PATH.unlink()

    mock_proc = AsyncMock()
    mock_proc.returncode = None  # Process is running (not exited)
    mock_proc.pid = 99999

    async def side_effect(*args, **kwargs):
        vpn.PID_PATH.write_text(str(os.getpid()))
        return mock_proc

    with patch(
        "asyncio.create_subprocess_exec", side_effect=side_effect
    ) as mock_exec, patch.object(
        VpnManager, "connected", new_callable=PropertyMock
    ) as mock_connected:
        # First call: not connected (triggers _kill_existing check), then True
        mock_connected.side_effect = [False, True]

        await vpn.connect()
        assert mock_exec.called


@pytest.mark.asyncio
async def test_vpn_manager_disconnect():
    """Disconnect terminates the managed process and waits for exit."""
    vpn = VpnManager()

    # Simulate a running process
    mock_proc = MagicMock()
    mock_proc.returncode = None  # Still running
    mock_proc.pid = 99999
    mock_proc.terminate = MagicMock()
    mock_proc.kill = MagicMock()

    wait_future = asyncio.get_event_loop().create_future()
    wait_future.set_result(0)
    mock_proc.wait = MagicMock(return_value=wait_future)

    vpn._process = mock_proc

    await vpn.disconnect()

    mock_proc.terminate.assert_called_once()
    assert vpn._auto_disconnect_task is None


def test_vpn_endpoints(client):
    # 1. Check status initially (not uploaded)
    resp = client.get("/control/vpn/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["uploaded"] is False
    assert data["connected"] is False

    # 2. Upload file
    file_content = b"client-config-data"
    resp = client.post(
        "/control/vpn/upload",
        files={"file": ("client.ovpn", file_content, "application/x-openvpn")},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "uploaded"

    # 3. Check status again (should be uploaded)
    resp = client.get("/control/vpn/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["uploaded"] is True
    assert data["size"] == len(file_content)

    # 4. Connect (fails with 500 or 400 because openvpn is not installed in local test environment,
    # but we can verify it reaches start connection logic)
    resp = client.post("/control/vpn/connect")
    # File exists but openvpn binary missing/fails on dev machine -> 500 or RuntimeError
    assert resp.status_code in (400, 500)

    # 5. Delete file
    resp = client.delete("/control/vpn/upload")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # 6. Check status again (should be False)
    resp = client.get("/control/vpn/status")
    assert resp.status_code == 200
    assert resp.json()["uploaded"] is False


@pytest.mark.asyncio
async def test_vpn_safety_timer_auto_disconnects():
    """Safety timer fires and calls disconnect after max_connected_minutes."""
    vpn = VpnManager()
    vpn.set_max_connected_minutes(1)  # 1 minute

    with patch.object(VpnManager, "connected", new_callable=PropertyMock, return_value=True):
        await vpn.connect()  # Should start safety timer

    # Verify the timer task was created
    assert vpn._auto_disconnect_task is not None
    assert not vpn._auto_disconnect_task.done()

    # Cancel it for cleanup (we don't want to actually wait 60s)
    vpn._cancel_safety_timer()
    assert vpn._auto_disconnect_task is None


@pytest.mark.asyncio
async def test_vpn_disconnect_cancels_safety_timer():
    """Explicit disconnect cancels the safety timer."""
    vpn = VpnManager()
    vpn.set_max_connected_minutes(45)

    with patch.object(VpnManager, "connected", new_callable=PropertyMock, return_value=True):
        await vpn.connect()

    assert vpn._auto_disconnect_task is not None

    # Simulate disconnect with a mock process
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.pid = 99999
    mock_proc.terminate = MagicMock()
    wait_future = asyncio.get_event_loop().create_future()
    wait_future.set_result(0)
    mock_proc.wait = MagicMock(return_value=wait_future)
    vpn._process = mock_proc

    await vpn.disconnect()

    # Timer should be cancelled after disconnect
    assert vpn._auto_disconnect_task is None


@pytest.mark.asyncio
async def test_vpn_no_timer_when_disabled():
    """No safety timer when max_connected_minutes is 0."""
    vpn = VpnManager()
    vpn.set_max_connected_minutes(0)

    with patch.object(VpnManager, "connected", new_callable=PropertyMock, return_value=True):
        await vpn.connect()

    assert vpn._auto_disconnect_task is None

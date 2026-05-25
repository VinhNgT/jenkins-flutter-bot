import os
import signal
from unittest.mock import AsyncMock, patch, PropertyMock

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
async def test_vpn_manager_connect_already_connected(tmp_path):
    vpn = VpnManager()
    vpn.OVPN_PATH.parent.mkdir(parents=True, exist_ok=True)
    vpn.OVPN_PATH.write_text("client-config")
    vpn.PID_PATH.write_text(str(os.getpid()))

    # Patch connected so the test doesn't depend on /sys/class/net existing
    # (absent on macOS) or a real tun interface being present (Linux without VPN).
    with patch.object(VpnManager, "connected", new_callable=PropertyMock, return_value=True):
        await vpn.connect()  # Should return early without spawning openvpn


@pytest.mark.asyncio
async def test_vpn_manager_connect_success(tmp_path):
    vpn = VpnManager()
    vpn.OVPN_PATH.parent.mkdir(parents=True, exist_ok=True)
    vpn.OVPN_PATH.write_text("client-config")

    if vpn.PID_PATH.exists():
        vpn.PID_PATH.unlink()

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    async def side_effect(*args, **kwargs):
        # Simulate PID file creation by openvpn
        vpn.PID_PATH.write_text(str(os.getpid()))
        return mock_proc

    with patch(
        "asyncio.create_subprocess_exec", side_effect=side_effect
    ) as mock_exec, patch.object(
        VpnManager, "connected", new_callable=PropertyMock
    ) as mock_connected:
        # Make self.connected return False first (to trigger execution), then True to simulate tun up
        mock_connected.side_effect = [False, True]

        await vpn.connect()
        assert mock_exec.called
        assert vpn.PID_PATH.exists()



@pytest.mark.asyncio
async def test_vpn_manager_disconnect(tmp_path):
    vpn = VpnManager()
    vpn.PID_PATH.write_text(str(os.getpid()))

    with patch("os.kill") as mock_kill:
        await vpn.disconnect()
        mock_kill.assert_any_call(os.getpid(), signal.SIGTERM)
        assert not vpn.PID_PATH.exists()


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

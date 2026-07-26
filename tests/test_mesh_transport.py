"""Tests del transporte MESH — sockets UNIX reales."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from eidos.mesh.protocol import MeshMessage, MessageType, pub, request, response
from eidos.mesh.transport import (
    MeshClient,
    MeshServer,
    TransportError,
    socket_path_for,
)


@pytest.fixture
def runtime_dir(tmp_path: Path) -> Path:
    return tmp_path / "runtime"


class TestSocketPathFor:
    def test_generates_path_with_node_id(self, runtime_dir: Path) -> None:
        p = socket_path_for("node-abc-123", runtime_dir)
        assert "node-abc-123" in str(p)
        assert p.suffix == ".sock"
        assert runtime_dir.exists()  # crea el dir si no existe

    def test_sanitizes_unsafe_chars(self, runtime_dir: Path) -> None:
        p = socket_path_for("node/with:colons", runtime_dir)
        assert "/" not in p.name
        assert ":" not in p.name


class TestMeshServer:
    def test_server_starts_and_stops(self, runtime_dir: Path) -> None:
        sock_path = socket_path_for("test-server", runtime_dir)
        received: list[MeshMessage] = []

        def handler(msg: MeshMessage, conn) -> None:
            received.append(msg)

        server = MeshServer(socket_path=sock_path, handler=handler)
        server.start()
        time.sleep(0.1)  # dar tiempo al acceptor thread
        assert server.socket_path.exists()
        server.stop()
        assert not sock_path.exists()

    def test_server_receives_message(self, runtime_dir: Path) -> None:
        sock_path = socket_path_for("test-recv", runtime_dir)
        received: list[MeshMessage] = []
        event = threading.Event()

        def handler(msg: MeshMessage, conn) -> None:
            received.append(msg)
            event.set()

        server = MeshServer(socket_path=sock_path, handler=handler)
        server.start()
        time.sleep(0.1)

        msg = pub(source="client", topic="test", params={"hello": "world"})
        MeshClient.send_message(sock_path, msg, timeout=2.0)

        assert event.wait(timeout=2.0), "Server should have received the message"
        assert len(received) == 1
        assert received[0].topic == "test"
        assert received[0].params == {"hello": "world"}

        server.stop()

    def test_server_handles_multiple_messages(self, runtime_dir: Path) -> None:
        sock_path = socket_path_for("test-multi", runtime_dir)
        received: list[MeshMessage] = []
        event = threading.Event()
        count = [0]

        def handler(msg: MeshMessage, conn) -> None:
            received.append(msg)
            count[0] += 1
            if count[0] >= 3:
                event.set()

        server = MeshServer(socket_path=sock_path, handler=handler)
        server.start()
        time.sleep(0.1)

        for i in range(3):
            msg = pub(source="c", topic="t", params={"i": i})
            MeshClient.send_message(sock_path, msg, timeout=2.0)
            time.sleep(0.05)

        assert event.wait(timeout=3.0), f"Should have received 3 messages, got {count[0]}"
        assert len(received) == 3

        server.stop()


class TestMeshClient:
    def test_send_message_to_nonexistent_socket_raises(
        self, runtime_dir: Path
    ) -> None:
        sock_path = runtime_dir / "nonexistent.sock"
        msg = pub(source="x", topic="t")
        with pytest.raises(TransportError):
            MeshClient.send_message(sock_path, msg, timeout=1.0)

    def test_send_request_gets_response(self, runtime_dir: Path) -> None:
        sock_path = socket_path_for("test-req-resp", runtime_dir)

        def handler(msg: MeshMessage, conn) -> None:
            if msg.type == MessageType.REQUEST:
                resp = response(
                    source="server",
                    in_reply_to=msg.id,
                    params={"ack": True},
                    target=msg.source,
                )
                conn.sendall((resp.to_json() + "\n").encode("utf-8"))

        server = MeshServer(socket_path=sock_path, handler=handler)
        server.start()
        time.sleep(0.1)

        req = request(source="client", method="hello", params={"x": 1})
        resp = MeshClient.send_request(sock_path, req, timeout=2.0)

        assert resp.type == MessageType.RESPONSE
        assert resp.in_reply_to == req.id
        assert resp.params == {"ack": True}

        server.stop()

    def test_send_request_timeout_raises(self, runtime_dir: Path) -> None:
        sock_path = socket_path_for("test-timeout", runtime_dir)

        # Handler que NO responde
        def handler(msg: MeshMessage, conn) -> None:
            pass  # no response

        server = MeshServer(socket_path=sock_path, handler=handler)
        server.start()
        time.sleep(0.1)

        req = request(source="client", method="hello")
        from eidos.mesh.transport import TransportTimeout

        with pytest.raises(TransportTimeout):
            MeshClient.send_request(sock_path, req, timeout=1.0)

        server.stop()

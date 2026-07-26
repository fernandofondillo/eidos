"""Transporte del MESH — Fase 4.

Servidor y cliente de sockets UNIX. Cada instancia EIDOS hace bind en
`unix://<runtime_dir>/eidos-<pid>.sock` y acepta conexiones entrantes.

Modelo: 1 socket por par (sender → receiver). Cada mensaje se envía como
una línea JSON terminada en `\\n` (newline-delimited JSON). Esto permite
streaming simple sin framing complejo.

En Windows el transporte sería named pipes (`\\\\.\\pipe\\eidos`), pero
v1 es POSIX-only (entorno primario macOS).
"""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable

from eidos.mesh.protocol import MeshMessage
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class TransportError(Exception):
    """Error de transporte (bind, connect, send, recv)."""


class TransportTimeout(TransportError):
    """Timeout en recv o connect."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def socket_path_for(node_id: str, runtime_dir: Path) -> Path:
    """Devuelve la ruta del socket UNIX para un node_id.

    Para que sea predecible y permitir que otras instancias lo encuentren,
    usamos un hash corto del node_id + pid opcional.
    """
    runtime_dir.mkdir(parents=True, exist_ok=True)
    # Sanitizar node_id para filesystem (UUIDs ya son safe)
    safe = node_id.replace("/", "_").replace(":", "_")
    return runtime_dir / f"eidos-{safe}.sock"


# ---------------------------------------------------------------------------
# MeshServer — acepta conexiones entrantes
# ---------------------------------------------------------------------------


class MeshServer:
    """Servidor de sockets UNIX. Acepta conexiones y procesa mensajes en hilos."""

    def __init__(
        self,
        socket_path: Path,
        handler: Callable[[MeshMessage, "socket.socket"], None],
    ) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._client_threads: list[threading.Thread] = []

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def address(self) -> str:
        return f"unix://{self._socket_path}"

    def start(self) -> None:
        """Crea el socket, bind, listen y arranca el hilo acceptor."""
        # Limpiar socket stale
        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except OSError:
                pass

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(str(self._socket_path))
            self._sock.listen(16)
            self._sock.settimeout(0.5)  # polling para stop event
        except OSError as e:
            self._sock.close()
            raise TransportError(f"Failed to bind {self._socket_path}: {e}") from e

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._accept_loop,
            name=f"mesh-server-{self._socket_path.stem}",
            daemon=True,
        )
        self._thread.start()
        logger.info("mesh_server_started", address=self.address)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        # Limpiar socket file
        try:
            if self._socket_path.exists():
                self._socket_path.unlink()
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        # Esperar client threads
        for t in self._client_threads:
            if t.is_alive():
                t.join(timeout=0.5)
        self._client_threads.clear()
        logger.info("mesh_server_stopped", address=self.address)

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # socket cerrado
            t = threading.Thread(
                target=self._handle_client,
                args=(conn,),
                name=f"mesh-client-{conn.fileno()}",
                daemon=True,
            )
            t.start()
            self._client_threads.append(t)

    def _handle_client(self, conn: socket.socket) -> None:
        """Lee mensajes newline-delimited de una conexión y los pasa al handler."""
        try:
            buf = b""
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                buf += data
                # Procesar mensajes completos (separados por \n)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = MeshMessage.from_json(line)
                        self._handler(msg, conn)
                    except Exception as e:
                        logger.warning("mesh_message_parse_failed", error=str(e))
        finally:
            try:
                conn.close()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# MeshClient — envía mensajes a un peer
# ---------------------------------------------------------------------------


class MeshClient:
    """Cliente para enviar mensajes a otro nodo vía socket UNIX."""

    @staticmethod
    def send_message(
        socket_path: Path,
        msg: MeshMessage,
        timeout: float = 5.0,
    ) -> None:
        """Envía un mensaje fire-and-forget. Lanza TransportError si falla."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(str(socket_path))
            sock.sendall((msg.to_json() + "\n").encode("utf-8"))
        except (socket.timeout, OSError) as e:
            raise TransportError(f"Failed to send to {socket_path}: {e}") from e
        finally:
            try:
                sock.close()
            except OSError:
                pass

    @staticmethod
    def send_request(
        socket_path: Path,
        msg: MeshMessage,
        timeout: float = 10.0,
    ) -> MeshMessage:
        """Envía un request y espera la response. Devuelve el MeshMessage respuesta."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(str(socket_path))
            sock.sendall((msg.to_json() + "\n").encode("utf-8"))
            # Leer una línea (la response)
            buf = b""
            while b"\n" not in buf:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
            if not buf:
                raise TransportTimeout("No response received")
            line = buf.split(b"\n", 1)[0]
            return MeshMessage.from_json(line)
        except socket.timeout as e:
            raise TransportTimeout(f"Timeout waiting for response from {socket_path}") from e
        except OSError as e:
            raise TransportError(f"Failed request to {socket_path}: {e}") from e
        finally:
            try:
                sock.close()
            except OSError:
                pass


__all__ = [
    "MeshServer",
    "MeshClient",
    "TransportError",
    "TransportTimeout",
    "socket_path_for",
]

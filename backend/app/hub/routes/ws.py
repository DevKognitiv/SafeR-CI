"""Realtime WebSocket: ``/ws?token=&home_id=`` streams hub events to the SafeR app.

Server -> client messages are ``HubEvent.to_ws()`` payloads (``device.state``, ``device.event``, ``message.new``,
``security.mode``, ``security.alarm``, ``scene.ran``, ``device.added``, ``device.removed``...) filtered by home:
events carrying ``home_id=None`` are broadcast to every connection. A ``hello`` frame is sent first.

Client -> server: ``{"type": "ping"}`` -> ``{"type": "pong"}`` and ``{"type": "subscribe", "home_id": ...}`` to
switch home without reconnecting (``home_id: null`` = every home of the user).

Authentication failures close the socket with application codes 4401 (bad/missing token) and 4403 (not a member
of the requested home). The socket is accepted before it is closed so real ASGI servers deliver the close code to
the client (a close before ``accept`` degrades to a bare HTTP 403 handshake failure).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import __version__
from app.hub import events as ev
from app.hub.deps import websocket_user
from app.hub.models import HomeMember
from app.hub.runtime import HubRuntime, get_runtime

logger = logging.getLogger("safer.hub.ws")

router = APIRouter()

__all__ = ["router", "Connection", "WS_UNAUTHORIZED", "WS_FORBIDDEN"]

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
QUEUE_SIZE = 512  # outgoing frames buffered per connection before the slowest ones are dropped
# Internal bus events that must never reach clients
INTERNAL_EVENT_TYPES = {ev.TICK}


class Connection:
    """One WebSocket client: home filter, outgoing queue and the task draining it to the socket."""

    def __init__(self, websocket: WebSocket, user_id: str, home_ids: Set[str], home_id: Optional[str] = None):
        self.websocket = websocket
        self.user_id = user_id
        self.home_ids: Set[str] = set(home_ids)
        self.home_id = home_id
        self.queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.sent = 0
        self.dropped = 0
        self._sender: Optional["asyncio.Task[None]"] = None
        self._unsubscribe: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------ filtering
    def wants(self, event: ev.HubEvent) -> bool:
        """True when ``event`` must be forwarded to this client."""
        if event.type in INTERNAL_EVENT_TYPES:
            return False
        return event.home_id is None or event.home_id in self.home_ids

    async def on_event(self, event: ev.HubEvent) -> None:
        """Bus subscriber: enqueue matching events (never blocks the publisher)."""
        if self.wants(event):
            self.enqueue(event.to_ws())

    def enqueue(self, message: Dict[str, Any]) -> None:
        """Queue a frame for the sender task; drops (and counts) when the client is too slow."""
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                logger.warning("ws: client %s too slow, %d frame(s) dropped", self.user_id, self.dropped)

    # ------------------------------------------------------------------ lifecycle
    def start(self, runtime: HubRuntime) -> None:
        """Subscribe to the bus and start the sender task."""
        self._unsubscribe = runtime.bus.subscribe(self.on_event)
        self._sender = asyncio.create_task(self._send_loop(), name=f"safer-hub-ws-{self.user_id}")

    async def _send_loop(self) -> None:
        try:
            while True:
                message = await self.queue.get()
                if message is None:
                    return
                await self.websocket.send_json(message)
                self.sent += 1
        except asyncio.CancelledError:
            raise
        except (WebSocketDisconnect, RuntimeError, OSError) as exc:
            # RuntimeError: send after close / connection already closed by the client
            logger.debug("ws: sender for %s stopped: %s", self.user_id, exc)
        except Exception:  # pylint: disable=broad-except
            logger.exception("ws: sender for %s crashed", self.user_id)

    async def close(self) -> None:
        """Unsubscribe from the bus and stop the sender task (idempotent)."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        sender, self._sender = self._sender, None
        if sender is not None and not sender.done():
            sender.cancel()
            try:
                await sender
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass


# ---------------------------------------------------------------------------- helpers
async def _member_home_ids(session: AsyncSession, user_id: str) -> Set[str]:
    rows = await session.execute(select(HomeMember.home_id).where(HomeMember.user_id == user_id))
    return {home_id for (home_id,) in rows.all()}


async def _reject(websocket: WebSocket, code: int, reason: str) -> None:
    """Close the handshake with an application close code the client can read."""
    try:
        await websocket.accept()
        await websocket.close(code=code, reason=reason)
    except (WebSocketDisconnect, RuntimeError, OSError):  # client already gone
        pass


async def _receive_frame(websocket: WebSocket) -> str:
    """Next client frame as text (binary frames are decoded as UTF-8); raises ``WebSocketDisconnect``.

    ``WebSocket.receive_text`` raises ``KeyError`` on a binary frame under uvicorn; mobile WebSocket
    libraries occasionally send JSON as binary, so both frame types are accepted here.
    """
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000), message.get("reason"))
    text = message.get("text")
    if text is not None:
        return text
    return (message.get("bytes") or b"").decode("utf-8", errors="replace")


async def _handle_client_message(runtime: HubRuntime, connection: Connection, raw: str) -> None:
    """Dispatch one client frame (ping / subscribe); errors are reported as ``{"type": "error"}`` frames."""
    try:
        message = json.loads(raw)
    except ValueError:
        connection.enqueue({"type": "error", "detail": "Invalid JSON"})
        return
    if not isinstance(message, dict):
        connection.enqueue({"type": "error", "detail": "Expected a JSON object"})
        return
    mtype = message.get("type")
    if mtype == "ping":
        reply: Dict[str, Any] = {"type": "pong"}
        if message.get("ts") is not None:
            reply["ts"] = message["ts"]
        connection.enqueue(reply)
    elif mtype == "subscribe":
        target = message.get("home_id")
        async with runtime.db.session() as session:
            homes = await _member_home_ids(session, connection.user_id)
        if target is None:
            connection.home_ids, connection.home_id = homes, None
        elif target in homes:
            connection.home_ids, connection.home_id = {target}, target
        else:
            connection.enqueue({"type": "error", "detail": "Not a member of this home", "home_id": target})
            return
        connection.enqueue({"type": "subscribed", "home_id": connection.home_id})
    else:
        connection.enqueue({"type": "error", "detail": f"Unknown message type '{mtype}'"})


# ---------------------------------------------------------------------------- route
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Realtime feed for one user, filtered by ``home_id`` (or every home of the user when omitted)."""
    runtime = get_runtime()
    home_id = (websocket.query_params.get("home_id") or "").strip() or None
    async with runtime.db.session() as session:
        user = await websocket_user(websocket, session)
        if user is None:
            await _reject(websocket, WS_UNAUTHORIZED, "Invalid or missing token")
            return
        home_ids = await _member_home_ids(session, user.id)
    if home_id is not None:
        if home_id not in home_ids:
            await _reject(websocket, WS_FORBIDDEN, "Not a member of this home")
            return
        home_ids = {home_id}

    await websocket.accept()
    connection = Connection(websocket, user.id, home_ids, home_id)
    connection.enqueue({"type": "hello", "home_id": home_id, "version": __version__, "user_id": user.id})
    connection.start(runtime)
    logger.info("ws: %s connected (home=%s)", user.id, home_id or "*")
    try:
        while True:
            raw = await _receive_frame(websocket)
            await _handle_client_message(runtime, connection, raw)
    except WebSocketDisconnect as exc:
        logger.info("ws: %s disconnected (code=%s, sent=%d, dropped=%d)", user.id, exc.code, connection.sent, connection.dropped)
    except RuntimeError as exc:  # receive after the socket was closed underneath us
        logger.debug("ws: %s receive loop ended: %s", user.id, exc)
    finally:
        await connection.close()

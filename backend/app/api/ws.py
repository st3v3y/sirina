from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._meetings: dict[int, set[WebSocket]] = {}
        self._status: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect_meeting(self, meeting_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._meetings.setdefault(meeting_id, set()).add(ws)

    async def disconnect_meeting(self, meeting_id: int, ws: WebSocket) -> None:
        async with self._lock:
            if meeting_id in self._meetings:
                self._meetings[meeting_id].discard(ws)
                if not self._meetings[meeting_id]:
                    del self._meetings[meeting_id]

    async def broadcast_meeting(self, meeting_id: int, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, default=str)
        async with self._lock:
            conns = list(self._meetings.get(meeting_id, ()))
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                log.exception("ws send failed")

    async def connect_status(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._status.add(ws)

    async def disconnect_status(self, ws: WebSocket) -> None:
        async with self._lock:
            self._status.discard(ws)

    async def broadcast_status(self, payload: dict[str, Any]) -> None:
        text = json.dumps({"type": "status", "payload": payload}, default=str)
        async with self._lock:
            conns = list(self._status)
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/ws/meetings/{meeting_id}")
async def ws_meeting(websocket: WebSocket, meeting_id: int) -> None:
    await manager.connect_meeting(meeting_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_meeting(meeting_id, websocket)


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    await manager.connect_status(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_status(websocket)

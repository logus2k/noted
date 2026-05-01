import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
from app.config import CELL_LOCK_TTL_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class CellLock:
    owner_sid: str
    owner_name: str
    cell_index: int
    acquired_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default=None)

    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = self.acquired_at + timedelta(seconds=CELL_LOCK_TTL_SECONDS)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    def renew(self):
        self.expires_at = datetime.utcnow() + timedelta(seconds=CELL_LOCK_TTL_SECONDS)

    def to_dict(self) -> dict:
        return {
            "owner_sid": self.owner_sid,
            "owner_name": self.owner_name,
            "cell_index": self.cell_index,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat()
        }


@dataclass
class RoomState:
    room_id: str
    project_id: str
    notebook_path: str
    clients: dict[str, dict] = field(default_factory=dict)
    cell_locks: dict[int, CellLock] = field(default_factory=dict)


class CollaborationManager:
    """Manages real-time multi-user editing of notebooks."""

    def __init__(self, sio):
        self._sio = sio
        self._rooms: dict[str, RoomState] = {}

    def _room_id(self, project_id: str, notebook_path: str) -> str:
        return f"notebook:{project_id}:{notebook_path}"

    def get_room(self, project_id: str, notebook_path: str) -> Optional[RoomState]:
        return self._rooms.get(self._room_id(project_id, notebook_path))

    async def join_room(self, sid: str, project_id: str, notebook_path: str,
                        user_name: str = "Anonymous") -> RoomState:
        room_id = self._room_id(project_id, notebook_path)
        if room_id not in self._rooms:
            self._rooms[room_id] = RoomState(
                room_id=room_id, project_id=project_id,
                notebook_path=notebook_path
            )
        room = self._rooms[room_id]
        room.clients[sid] = {
            "name": user_name,
            "joined_at": datetime.utcnow().isoformat()
        }
        await self._sio.enter_room(sid, room_id)
        await self._sio.emit("user:joined", {
            "sid": sid, "name": user_name, "notebook_key": room_id
        }, room=room_id, skip_sid=sid)
        logger.info(f"Client {sid} joined room {room_id}")
        return room

    async def leave_room(self, sid: str, project_id: str, notebook_path: str):
        room_id = self._room_id(project_id, notebook_path)
        room = self._rooms.get(room_id)
        if not room:
            return
        user_info = room.clients.pop(sid, {})
        await self._release_locks_for_sid(room, sid)
        await self._sio.leave_room(sid, room_id)
        await self._sio.emit("user:left", {
            "sid": sid, "name": user_info.get("name", "Anonymous"),
            "notebook_key": room_id
        }, room=room_id)
        if not room.clients:
            del self._rooms[room_id]
            logger.info(f"Room {room_id} removed (empty)")
        logger.info(f"Client {sid} left room {room_id}")

    async def leave_all_rooms(self, sid: str):
        rooms_to_leave = []
        for room in self._rooms.values():
            if sid in room.clients:
                rooms_to_leave.append((room.project_id, room.notebook_path))
        for project_id, notebook_path in rooms_to_leave:
            await self.leave_room(sid, project_id, notebook_path)

    async def acquire_lock(self, sid: str, project_id: str,
                           notebook_path: str, cell_index: int,
                           user_name: str = "Anonymous") -> bool:
        room_id = self._room_id(project_id, notebook_path)
        room = self._rooms.get(room_id)
        if not room:
            return False
        existing = room.cell_locks.get(cell_index)
        if existing and not existing.is_expired and existing.owner_sid != sid:
            return False
        lock = CellLock(owner_sid=sid, owner_name=user_name, cell_index=cell_index)
        room.cell_locks[cell_index] = lock
        await self._sio.emit("cell:lock_changed", {
            "cell_index": cell_index, "owner": user_name,
            "owner_sid": sid, "locked": True,
            "notebook_key": room_id
        }, room=room_id)
        return True

    async def release_lock(self, sid: str, project_id: str,
                           notebook_path: str, cell_index: int) -> bool:
        room_id = self._room_id(project_id, notebook_path)
        room = self._rooms.get(room_id)
        if not room:
            return False
        existing = room.cell_locks.get(cell_index)
        if not existing or existing.owner_sid != sid:
            return False
        del room.cell_locks[cell_index]
        await self._sio.emit("cell:lock_changed", {
            "cell_index": cell_index, "owner": None,
            "owner_sid": None, "locked": False,
            "notebook_key": room_id
        }, room=room_id)
        return True

    def renew_locks(self, sid: str):
        for room in self._rooms.values():
            for lock in room.cell_locks.values():
                if lock.owner_sid == sid:
                    lock.renew()

    async def _release_locks_for_sid(self, room: RoomState, sid: str) -> list[int]:
        released = []
        to_remove = [
            idx for idx, lock in room.cell_locks.items()
            if lock.owner_sid == sid
        ]
        for idx in to_remove:
            del room.cell_locks[idx]
            released.append(idx)
            await self._sio.emit("cell:lock_changed", {
                "cell_index": idx, "owner": None,
                "owner_sid": None, "locked": False,
                "notebook_key": room.room_id
            }, room=room.room_id)
        return released

    async def broadcast_cell_update(self, sid: str, project_id: str,
                                    notebook_path: str, cell_index: int,
                                    source: str):
        room_id = self._room_id(project_id, notebook_path)
        await self._sio.emit("cell:updated", {
            "cell_index": cell_index, "source": source, "by_sid": sid,
            "notebook_key": room_id
        }, room=room_id, skip_sid=sid)

    async def broadcast_cell_add(self, sid: str, project_id: str,
                                 notebook_path: str, cell_index: int,
                                 cell_type: str, cell_id: str):
        room_id = self._room_id(project_id, notebook_path)
        await self._sio.emit("cell:added", {
            "cell_index": cell_index, "cell_type": cell_type,
            "cell_id": cell_id, "by_sid": sid,
            "notebook_key": room_id
        }, room=room_id, skip_sid=sid)

    async def broadcast_cell_delete(self, sid: str, project_id: str,
                                    notebook_path: str, cell_index: int):
        room_id = self._room_id(project_id, notebook_path)
        await self._sio.emit("cell:deleted", {
            "cell_index": cell_index, "by_sid": sid,
            "notebook_key": room_id
        }, room=room_id, skip_sid=sid)

    async def broadcast_cell_move(self, sid: str, project_id: str,
                                  notebook_path: str, from_index: int,
                                  to_index: int):
        room_id = self._room_id(project_id, notebook_path)
        await self._sio.emit("cell:moved", {
            "from_index": from_index, "to_index": to_index, "by_sid": sid,
            "notebook_key": room_id
        }, room=room_id, skip_sid=sid)

    def get_room_state(self, project_id: str, notebook_path: str) -> dict:
        room_id = self._room_id(project_id, notebook_path)
        room = self._rooms.get(room_id)
        if not room:
            return {"clients": {}, "cell_locks": {}}
        return {
            "clients": room.clients,
            "cell_locks": {
                idx: lock.to_dict()
                for idx, lock in room.cell_locks.items()
                if not lock.is_expired
            }
        }

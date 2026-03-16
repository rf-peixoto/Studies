from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

rooms: Dict[str, "Room"] = {}
participants_by_sid: Dict[str, tuple[str, str]] = {}
ip_failures: Dict[str, List[datetime]] = {}
ip_blocks: Dict[str, datetime] = {}
ip_room_creations: Dict[str, List[datetime]] = {}
ip_password_failures: Dict[str, List[datetime]] = {}
local_pow_challenges: Dict[str, tuple[str, datetime]] = {}

@dataclass
class Participant:
    sid: str
    username: str
    public_key: str
    joined_at: datetime
    last_seen: datetime

@dataclass
class StoredMessage:
    sender_public_key: str
    recipient_public_key: str
    ciphertext: str
    iv: str
    timestamp: datetime

@dataclass
class Room:
    id: str
    capacity: int
    expiry: datetime
    password_hash: str | None = None
    participants: Dict[str, Participant] = field(default_factory=dict)
    messages: List[StoredMessage] = field(default_factory=list)

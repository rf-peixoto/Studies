import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List

ROOM_ID_REGEX = re.compile(r'^[a-f0-9]{64}$')
USERNAME_REGEX = re.compile(r'^[A-Za-z0-9_-]{1,12}$')
RESERVED_USERNAMES = {'system', 'admin', 'server', 'moderator'}


def utcnow() -> datetime:
    return datetime.utcnow()


def validate_room_id(room_id: str) -> bool:
    return bool(ROOM_ID_REGEX.fullmatch((room_id or '').strip().lower()))


def validate_username(username: str) -> bool:
    username = (username or '').strip()
    return bool(USERNAME_REGEX.fullmatch(username)) and username.lower() not in RESERVED_USERNAMES


def prune_attempts(storage: Dict[str, List[datetime]], ip: str, window_seconds: int) -> List[datetime]:
    now = utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    attempts = [t for t in storage.get(ip, []) if t > cutoff]
    storage[ip] = attempts
    return attempts


def is_rate_limited(ip: str, storage: Dict[str, List[datetime]], max_attempts: int, window_seconds: int) -> bool:
    attempts = prune_attempts(storage, ip, window_seconds)
    return len(attempts) >= max_attempts


def record_attempt(ip: str, storage: Dict[str, List[datetime]]):
    storage.setdefault(ip, []).append(utcnow())


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def verify_pow(challenge: str, solution: str, difficulty: int) -> bool:
    if not challenge or not solution:
        return False
    digest = sha256_hex(f'{challenge}:{solution}')
    return digest.startswith('0' * difficulty)

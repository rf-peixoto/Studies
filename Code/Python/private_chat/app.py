from __future__ import annotations

import secrets
from datetime import timedelta
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO, disconnect, emit, join_room as sio_join_room
from werkzeug.security import check_password_hash, generate_password_hash

from models import (
    Participant,
    Room,
    StoredMessage,
    ip_blocks,
    ip_failures,
    ip_password_failures,
    ip_room_creations,
    participants_by_sid,
    rooms,
)
from utils import (
    is_rate_limited,
    prune_attempts,
    record_attempt,
    utcnow,
    validate_room_id,
    validate_username,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', manage_session=True)

MAX_ACTIVE_ROOMS = 1000
MAX_ROOMS_PER_IP_PER_HOUR = 5
MAX_JOIN_FAILURES_PER_IP = 5
MAX_PASSWORD_FAILURES_PER_IP = 3
IP_BLOCK_SECONDS = 3600
PASSWORD_BLOCK_SECONDS = 3600
MESSAGE_TTL_SECONDS = 300
MAX_MESSAGE_LENGTH = 1000
ALLOWED_ROOM_SIZES = {8, 16, 32}
ALLOWED_DURATIONS = {8, 12, 16, 24}
POW_DIFFICULTY = 4
POW_THRESHOLD_CREATIONS = 3
POW_THRESHOLD_JOINS = 3


def get_client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    return forwarded or request.remote_addr or '0.0.0.0'


def clean_ip_state(ip: str):
    now = utcnow()
    prune_attempts(ip_room_creations, ip, 3600)
    prune_attempts(ip_failures, ip, 3600)
    prune_attempts(ip_password_failures, ip, 3600)
    if ip in ip_blocks and ip_blocks[ip] <= now:
        del ip_blocks[ip]


def current_room(room_id: str) -> Room | None:
    room = rooms.get(room_id)
    if not room:
        return None
    return room


def emit_participant_state(room_id: str):
    room = rooms.get(room_id)
    if not room:
        return
    payload = {
        'participants': [
            {
                'username': p.username,
                'publicKey': p.public_key,
            }
            for p in sorted(room.participants.values(), key=lambda item: item.joined_at)
        ],
        'count': len(room.participants),
        'capacity': room.capacity,
    }
    socketio.emit('participant_state', payload, room=room_id)


def purge_room_if_empty(room_id: str):
    room = rooms.get(room_id)
    if room and not room.participants:
        del rooms[room_id]


def record_join_failure(ip: str):
    record_attempt(ip, ip_failures)
    prune_attempts(ip_failures, ip, 3600)
    if len(ip_failures.get(ip, [])) >= MAX_JOIN_FAILURES_PER_IP:
        ip_blocks[ip] = utcnow() + timedelta(seconds=IP_BLOCK_SECONDS)


def record_password_failure(ip: str):
    record_attempt(ip, ip_password_failures)
    prune_attempts(ip_password_failures, ip, 3600)
    if len(ip_password_failures.get(ip, [])) >= MAX_PASSWORD_FAILURES_PER_IP:
        ip_blocks[ip] = utcnow() + timedelta(seconds=PASSWORD_BLOCK_SECONDS)


def block_remaining_seconds(ip: str) -> int:
    expires = ip_blocks.get(ip)
    if not expires:
        return 0
    delta = int((expires - utcnow()).total_seconds())
    return max(delta, 0)


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response




@app.route('/favicon.ico')
def favicon():
    return ('', 204)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/pow-challenge', methods=['GET'])
def pow_challenge():
    ip = get_client_ip()
    clean_ip_state(ip)
    creation_pressure = len(ip_room_creations.get(ip, [])) >= POW_THRESHOLD_CREATIONS
    join_pressure = len(ip_failures.get(ip, [])) >= POW_THRESHOLD_JOINS
    required = creation_pressure or join_pressure or len(rooms) >= int(MAX_ACTIVE_ROOMS * 0.85)
    challenge = secrets.token_hex(16)
    session['pow_challenge'] = challenge
    session['pow_required'] = required
    return jsonify({'required': required, 'difficulty': POW_DIFFICULTY if required else 0, 'challenge': challenge})


@app.route('/create_room', methods=['POST'])
def create_room():
    ip = get_client_ip()
    clean_ip_state(ip)

    if ip in ip_blocks and block_remaining_seconds(ip) > 0:
        return jsonify({'error': f'This IP is temporarily blocked for {block_remaining_seconds(ip)} seconds.'}), 403

    if len(rooms) >= MAX_ACTIVE_ROOMS:
        return jsonify({'error': 'Server at maximum room capacity. Try later.'}), 503

    if is_rate_limited(ip, ip_room_creations, MAX_ROOMS_PER_IP_PER_HOUR, 3600):
        return jsonify({'error': 'Too many rooms created from this IP in the last hour.'}), 429

    if session.get('pow_required'):
        challenge = session.get('pow_challenge', '')
        solution = request.form.get('pow_solution', '')
        from utils import verify_pow
        if not verify_pow(challenge, solution, POW_DIFFICULTY):
            return jsonify({'error': 'Proof-of-work verification failed.'}), 403

    username = request.form.get('username', '').strip()
    if not validate_username(username):
        return jsonify({'error': 'Invalid username. Use only a-z, A-Z, 0-9, - and _, max 12.'}), 400

    try:
        capacity = int(request.form.get('capacity', '0'))
        duration = int(request.form.get('duration', '0'))
    except ValueError:
        return jsonify({'error': 'Invalid room size or duration.'}), 400

    if capacity not in ALLOWED_ROOM_SIZES or duration not in ALLOWED_DURATIONS:
        return jsonify({'error': 'Invalid room size or duration.'}), 400

    password_protected = request.form.get('password_protected') == 'on'
    generated_password = secrets.token_hex(16) if password_protected else None
    password_hash = generate_password_hash(generated_password) if generated_password else None

    room_id = secrets.token_hex(32)
    expires_at = utcnow() + timedelta(hours=duration)
    rooms[room_id] = Room(id=room_id, capacity=capacity, expiry=expires_at, password_hash=password_hash)
    record_attempt(ip, ip_room_creations)

    session['username'] = username
    session['room_id'] = room_id
    session['room_password_visible'] = generated_password or ''
    session['created_room'] = room_id

    return jsonify({
        'room_id': room_id,
        'password': generated_password,
        'expires_at': expires_at.isoformat() + 'Z',
    })


@app.route('/join_room', methods=['POST'])
def join_room_route():
    ip = get_client_ip()
    clean_ip_state(ip)

    if ip in ip_blocks and block_remaining_seconds(ip) > 0:
        return jsonify({'error': f'This IP is temporarily blocked for {block_remaining_seconds(ip)} seconds.'}), 403

    if session.get('pow_required'):
        challenge = session.get('pow_challenge', '')
        solution = request.form.get('pow_solution', '')
        from utils import verify_pow
        if not verify_pow(challenge, solution, POW_DIFFICULTY):
            return jsonify({'error': 'Proof-of-work verification failed.'}), 403

    room_id = request.form.get('room_id', '').strip().lower()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not validate_room_id(room_id):
        record_join_failure(ip)
        return jsonify({'error': 'Invalid room ID format.'}), 400
    if not validate_username(username):
        return jsonify({'error': 'Invalid username. Use only a-z, A-Z, 0-9, - and _, max 12.'}), 400

    room = current_room(room_id)
    if not room:
        record_join_failure(ip)
        return jsonify({'error': 'Room not found.'}), 404
    if room.expiry <= utcnow():
        return jsonify({'error': 'Room has expired and no longer accepts new users.'}), 403
    if len(room.participants) >= room.capacity:
        return jsonify({'error': 'Room is full.'}), 403
    if any(p.username.lower() == username.lower() for p in room.participants.values()):
        return jsonify({'error': 'This username is already in use in the room.'}), 409

    if room.password_hash:
        if not password or not check_password_hash(room.password_hash, password):
            record_password_failure(ip)
            remaining = MAX_PASSWORD_FAILURES_PER_IP - len(ip_password_failures.get(ip, []))
            if remaining <= 0:
                return jsonify({'error': 'Too many wrong passwords. Blocked for one hour.'}), 403
            return jsonify({'error': f'Invalid password. {remaining} attempts remaining before 1-hour block.'}), 403

    session['username'] = username
    session['room_id'] = room_id
    session['room_password_visible'] = ''
    session.pop('created_room', None)
    return jsonify({'room_id': room_id, 'expires_at': room.expiry.isoformat() + 'Z'})


@app.route('/room/<room_id>')
def room_page(room_id: str):
    room_id = room_id.strip().lower()
    if not validate_room_id(room_id):
        abort(404)
    if session.get('room_id') != room_id or 'username' not in session:
        return redirect(url_for('index'))
    room = current_room(room_id)
    if not room:
        session.clear()
        return redirect(url_for('index'))
    password_banner = ''
    if session.get('created_room') == room_id:
        password_banner = session.get('room_password_visible', '')
    return render_template(
        'room.html',
        room_id=room_id,
        username=session['username'],
        expires_at=room.expiry.isoformat() + 'Z',
        password_banner=password_banner,
        capacity=room.capacity,
    )


@socketio.on('connect')
def handle_connect():
    room_id = session.get('room_id')
    username = session.get('username')
    if not room_id or not username:
        return False
    room = current_room(room_id)
    if not room:
        return False
    return True


@socketio.on('join')
def handle_join(data):
    room_id = session.get('room_id')
    username = session.get('username')
    public_key_b64 = (data or {}).get('publicKey', '')

    if not room_id or not username or not public_key_b64:
        disconnect()
        return

    room = current_room(room_id)
    if not room or room.expiry <= utcnow():
        emit('fatal', {'error': 'Room is unavailable.'})
        disconnect()
        return

    existing = participants_by_sid.get(request.sid)
    if existing:
        old_room_id, old_public_key = existing
        if old_room_id == room_id and old_public_key in room.participants:
            del room.participants[old_public_key]

    if len(room.participants) >= room.capacity:
        emit('fatal', {'error': 'Room is full.'})
        disconnect()
        return

    if any(p.username.lower() == username.lower() for p in room.participants.values()):
        emit('fatal', {'error': 'This username is already in use in the room.'})
        disconnect()
        return

    participant = Participant(
        sid=request.sid,
        username=username,
        public_key=public_key_b64,
        joined_at=utcnow(),
        last_seen=utcnow(),
    )
    room.participants[public_key_b64] = participant
    participants_by_sid[request.sid] = (room_id, public_key_b64)
    sio_join_room(room_id)

    emit_participant_state(room_id)

    recent_cutoff = utcnow() - timedelta(seconds=MESSAGE_TTL_SECONDS)
    for msg in [m for m in room.messages if m.recipient_public_key == public_key_b64 and m.timestamp > recent_cutoff]:
        emit('message', {
            'sender': msg.sender_public_key,
            'ciphertext': msg.ciphertext,
            'iv': msg.iv,
            'timestamp': msg.timestamp.isoformat() + 'Z',
        })


@socketio.on('message')
def handle_message(data):
    info = participants_by_sid.get(request.sid)
    if not info:
        return
    room_id, sender_pk = info
    room = current_room(room_id)
    if not room:
        return

    sender = room.participants.get(sender_pk)
    if sender:
        sender.last_seen = utcnow()

    recipients = (data or {}).get('recipients', [])
    if not isinstance(recipients, list):
        return

    now = utcnow()
    forwarded = 0
    for recipient in recipients:
        if forwarded >= room.capacity:
            break
        rcpt_pk = recipient.get('publicKey', '')
        ciphertext = recipient.get('ciphertext', '')
        iv = recipient.get('iv', '')
        if not rcpt_pk or not ciphertext or not iv:
            continue
        if len(ciphertext) > 10000 or len(iv) > 256:
            continue
        if rcpt_pk not in room.participants:
            continue
        room.messages.append(StoredMessage(
            sender_public_key=sender_pk,
            recipient_public_key=rcpt_pk,
            ciphertext=ciphertext,
            iv=iv,
            timestamp=now,
        ))
        socketio.emit('message', {
            'sender': sender_pk,
            'ciphertext': ciphertext,
            'iv': iv,
            'timestamp': now.isoformat() + 'Z',
        }, room=room.participants[rcpt_pk].sid)
        forwarded += 1

    cutoff = utcnow() - timedelta(seconds=MESSAGE_TTL_SECONDS)
    room.messages = [m for m in room.messages if m.timestamp > cutoff]


@socketio.on('typing_ping')
def handle_typing_ping():
    info = participants_by_sid.get(request.sid)
    if not info:
        return
    room_id, public_key = info
    room = current_room(room_id)
    if room and public_key in room.participants:
        room.participants[public_key].last_seen = utcnow()


@socketio.on('disconnect')
def handle_disconnect():
    info = participants_by_sid.pop(request.sid, None)
    if not info:
        return
    room_id, public_key = info
    room = current_room(room_id)
    if not room:
        return
    if public_key in room.participants:
        del room.participants[public_key]
    emit_participant_state(room_id)
    purge_room_if_empty(room_id)


def background_cleanup():
    while True:
        socketio.sleep(30)
        now = utcnow()
        cutoff = now - timedelta(seconds=MESSAGE_TTL_SECONDS)
        for room_id in list(rooms.keys()):
            room = rooms.get(room_id)
            if not room:
                continue
            room.messages = [m for m in room.messages if m.timestamp > cutoff]
            if room.expiry <= now and not room.participants:
                del rooms[room_id]
        for store in (ip_room_creations, ip_failures, ip_password_failures):
            for ip in list(store.keys()):
                prune_attempts(store, ip, 3600)
                if not store.get(ip):
                    store.pop(ip, None)
        for ip, expires in list(ip_blocks.items()):
            if expires <= now:
                ip_blocks.pop(ip, None)


socketio.start_background_task(background_cleanup)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)

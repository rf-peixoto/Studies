const roomConfig = document.getElementById('room-config');
if (!roomConfig) {
    throw new Error('Missing room configuration.');
}
const ROOM_ID = roomConfig.dataset.roomId;
const USERNAME = roomConfig.dataset.username;
const EXPIRES_AT = roomConfig.dataset.expiresAt;

let keyPair = null;
let privateKey = null;
let publicKeyB64 = null;
const sharedKeys = new Map();
const participants = new Map();

const messagesDiv = document.getElementById('messages');
const participantsList = document.getElementById('participants-list');
const messageInput = document.getElementById('message-input');
const participantCountSpan = document.getElementById('participant-count');
const expiryEl = document.getElementById('expiry');

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function addLine(className, html, ttlMs = 5 * 60 * 1000) {
    const div = document.createElement('div');
    div.className = 'message ' + className;
    div.innerHTML = html;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    setTimeout(() => div.remove(), ttlMs);
}

function formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function addSystemMessage(text, alert = false) {
    addLine(alert ? 'alert' : 'system', `<span class="timestamp">[${formatTime(new Date())}]</span> ${escapeHtml(text)}`);
}

function addChatMessage(sender, text, time = new Date()) {
    addLine('', `<span class="timestamp">[${formatTime(time)}]</span> <span class="sender">${escapeHtml(sender)}:</span> ${escapeHtml(text)}`);
}

function renderParticipants() {
    const ordered = Array.from(participants.values()).sort((a, b) => a.username.localeCompare(b.username));
    participantsList.innerHTML = ordered.map((p) => `<li>${escapeHtml(p.username)}${p.isSelf ? ' (you)' : ''}</li>`).join('');
    participantCountSpan.textContent = String(ordered.length);
}

async function deriveAesKey(sharedSecret) {
    const hkdfKey = await crypto.subtle.importKey('raw', sharedSecret, 'HKDF', false, ['deriveKey']);
    return crypto.subtle.deriveKey(
        {
            name: 'HKDF',
            hash: 'SHA-256',
            salt: new Uint8Array(0),
            info: new TextEncoder().encode('private-chat-room-v1'),
        },
        hkdfKey,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
    );
}

async function generateKeyPair() {
    const kp = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
    const rawPublic = await crypto.subtle.exportKey('raw', kp.publicKey);
    const pkcs8 = await crypto.subtle.exportKey('pkcs8', kp.privateKey);
    sessionStorage.setItem('keypair_' + ROOM_ID, JSON.stringify({
        publicKey: btoa(String.fromCharCode(...new Uint8Array(rawPublic))),
        privateKey: btoa(String.fromCharCode(...new Uint8Array(pkcs8))),
    }));
    keyPair = kp;
    privateKey = kp.privateKey;
    publicKeyB64 = btoa(String.fromCharCode(...new Uint8Array(rawPublic)));
}

async function restoreKeyPair() {
    const stored = sessionStorage.getItem('keypair_' + ROOM_ID);
    if (!stored) {
        await generateKeyPair();
        return;
    }
    try {
        const data = JSON.parse(stored);
        const rawPublic = Uint8Array.from(atob(data.publicKey), c => c.charCodeAt(0));
        privateKey = await crypto.subtle.importKey(
            'pkcs8',
            Uint8Array.from(atob(data.privateKey), c => c.charCodeAt(0)),
            { name: 'ECDH', namedCurve: 'P-256' },
            true,
            ['deriveBits']
        );
        const publicKey = await crypto.subtle.importKey('raw', rawPublic, { name: 'ECDH', namedCurve: 'P-256' }, true, []);
        keyPair = { publicKey, privateKey };
        publicKeyB64 = data.publicKey;
    } catch {
        sessionStorage.removeItem('keypair_' + ROOM_ID);
        await generateKeyPair();
    }
}

async function importAndDerive(peerPublicKeyB64) {
    const peerRaw = Uint8Array.from(atob(peerPublicKeyB64), c => c.charCodeAt(0));
    const peerKey = await crypto.subtle.importKey('raw', peerRaw, { name: 'ECDH', namedCurve: 'P-256' }, false, []);
    const bits = await crypto.subtle.deriveBits({ name: 'ECDH', public: peerKey }, privateKey, 256);
    return deriveAesKey(bits);
}

async function encryptFor(text, recipientPublicKey) {
    let aesKey = sharedKeys.get(recipientPublicKey);
    if (!aesKey) {
        aesKey = await importAndDerive(recipientPublicKey);
        sharedKeys.set(recipientPublicKey, aesKey);
    }
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(text);
    const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aesKey, encoded);
    return {
        ciphertext: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
        iv: btoa(String.fromCharCode(...iv)),
    };
}

async function decryptMessage(senderPublicKey, ciphertextB64, ivB64) {
    let aesKey = sharedKeys.get(senderPublicKey);
    if (!aesKey) {
        aesKey = await importAndDerive(senderPublicKey);
        sharedKeys.set(senderPublicKey, aesKey);
    }
    const ciphertext = Uint8Array.from(atob(ciphertextB64), c => c.charCodeAt(0));
    const iv = Uint8Array.from(atob(ivB64), c => c.charCodeAt(0));
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, aesKey, ciphertext);
    return new TextDecoder().decode(decrypted);
}

function updateExpiry() {
    const expires = new Date(EXPIRES_AT);
    const diff = expires.getTime() - Date.now();
    if (diff <= 0) {
        expiryEl.textContent = 'room expired';
        expiryEl.classList.add('warn');
        return;
    }
    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    expiryEl.textContent = `expires in ${hours}h ${minutes}m`;
    if (diff <= 3600000) {
        expiryEl.classList.add('warn');
    }
}
setInterval(updateExpiry, 10000);
updateExpiry();

const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', async () => {
    await restoreKeyPair();
    participants.clear();
    participants.set(publicKeyB64, { username: USERNAME, publicKey: publicKeyB64, isSelf: true });
    renderParticipants();
    socket.emit('join', { publicKey: publicKeyB64 });
});

socket.on('participant_state', async (payload) => {
    const incoming = Array.isArray(payload.participants) ? payload.participants : [];
    const currentSelf = participants.get(publicKeyB64) || { username: USERNAME, publicKey: publicKeyB64, isSelf: true };
    participants.clear();
    participants.set(publicKeyB64, currentSelf);

    for (const participant of incoming) {
        const isSelf = participant.publicKey === publicKeyB64;
        participants.set(participant.publicKey, { ...participant, isSelf });
        if (!isSelf) {
            try {
                const key = await importAndDerive(participant.publicKey);
                sharedKeys.set(participant.publicKey, key);
            } catch (error) {
                console.error('Failed deriving key for participant', error);
            }
        }
    }
    renderParticipants();
});

socket.on('message', async (data) => {
    try {
        const plain = await decryptMessage(data.sender, data.ciphertext, data.iv);
        const sender = participants.get(data.sender)?.username || 'unknown';
        addChatMessage(sender, plain, data.timestamp ? new Date(data.timestamp) : new Date());
    } catch (error) {
        console.error(error);
        addSystemMessage('Failed to decrypt one message.', true);
    }
});

socket.on('fatal', (data) => {
    addSystemMessage(data.error || 'Disconnected.', true);
    setTimeout(() => window.location.assign('/'), 1500);
});

socket.on('disconnect', () => {
    addSystemMessage('Disconnected from room.', true);
});

let typingTimer = null;
messageInput.addEventListener('input', () => {
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => socket.emit('typing_ping'), 250);
});

messageInput.addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter') {
        return;
    }
    event.preventDefault();
    const text = messageInput.value.trim();
    if (!text) {
        return;
    }
    messageInput.value = '';
    const recipients = [];
    for (const [publicKey, participant] of participants.entries()) {
        if (publicKey === publicKeyB64) {
            continue;
        }
        try {
            const encrypted = await encryptFor(text, publicKey);
            recipients.push({ publicKey, ...encrypted });
        } catch (error) {
            console.error('Encryption failed for recipient', participant.username, error);
        }
    }
    addChatMessage(USERNAME, text, new Date());
    if (recipients.length > 0) {
        socket.emit('message', { recipients });
    }
});

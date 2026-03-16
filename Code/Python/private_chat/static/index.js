const roomIdRegex = /^[a-f0-9]{64}$/;
const usernameRegex = /^[A-Za-z0-9_-]{1,12}$/;
const joinLockPrefix = 'join_lock_';

function showError(targetId, message) {
    const el = document.getElementById(targetId);
    if (el) {
        el.textContent = message || '';
    }
}

function validateFields(formData, isJoin = false) {
    const username = (formData.get('username') || '').trim();
    if (!usernameRegex.test(username)) {
        throw new Error('Invalid username. Use only a-z, A-Z, 0-9, - and _, max 12.');
    }
    if (isJoin) {
        const roomId = (formData.get('room_id') || '').trim().toLowerCase();
        if (!roomIdRegex.test(roomId)) {
            throw new Error('Room ID must be 64 lowercase hexadecimal characters.');
        }
        formData.set('room_id', roomId);
        const lockKey = joinLockPrefix + roomId;
        const lockedUntil = Number(localStorage.getItem(lockKey) || '0');
        if (lockedUntil > Date.now()) {
            const minutes = Math.ceil((lockedUntil - Date.now()) / 60000);
            throw new Error('This room entry is locally locked for about ' + minutes + ' more minute(s) after repeated wrong passwords.');
        }
    }
    formData.set('username', username);
}

async function fetchPowSolutionIfNeeded() {
    const response = await fetch('/pow-challenge', { credentials: 'same-origin' });
    const payload = await response.json();
    if (!payload.required) {
        return '';
    }
    const { challenge, difficulty } = payload;
    let nonce = 0;
    while (true) {
        const text = `${challenge}:${nonce}`;
        const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        const hex = Array.from(new Uint8Array(hashBuffer)).map((b) => b.toString(16).padStart(2, '0')).join('');
        if (hex.startsWith('0'.repeat(difficulty))) {
            return String(nonce);
        }
        nonce += 1;
    }
}

async function parseJsonSafe(response) {
    const text = await response.text();
    try {
        return JSON.parse(text);
    } catch {
        throw new Error(text || 'Invalid server response.');
    }
}

async function submitForm(url, formData, errorTarget, isJoin = false) {
    showError(errorTarget, '');
    validateFields(formData, isJoin);
    const submitButton = document.querySelector(url === '/create_room' ? '#create-submit' : '#join-submit');
    if (!submitButton) {
        throw new Error('Form button not found.');
    }
    submitButton.disabled = true;
    submitButton.textContent = 'working...';
    try {
        const powSolution = await fetchPowSolutionIfNeeded();
        if (powSolution) {
            formData.set('pow_solution', powSolution);
        }
        const response = await fetch(url, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'fetch' }
        });
        const data = await parseJsonSafe(response);
        if (!response.ok) {
            throw new Error(data.error || 'Request failed.');
        }
        return data;
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = url === '/create_room' ? 'generate room' : 'enter room';
    }
}

function attachHandlers() {
    const createForm = document.getElementById('create-form');
    const joinForm = document.getElementById('join-form');

    if (createForm) {
        createForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const formData = new FormData(event.currentTarget);
                const data = await submitForm('/create_room', formData, 'create-error', false);
                if (data.password) {
                    sessionStorage.setItem('room_password_' + data.room_id, data.password);
                }
                window.location.assign('/room/' + data.room_id);
            } catch (error) {
                showError('create-error', error.message);
            }
        });
    }

    if (joinForm) {
        joinForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            const roomId = (formData.get('room_id') || '').trim().toLowerCase();
            try {
                const data = await submitForm('/join_room', formData, 'join-error', true);
                localStorage.removeItem(joinLockPrefix + roomId);
                localStorage.removeItem('pw_fail_' + roomId);
                window.location.assign('/room/' + data.room_id);
            } catch (error) {
                const msg = error.message || 'Join failed.';
                if (/Invalid password|wrong passwords/i.test(msg)) {
                    const failKey = 'pw_fail_' + roomId;
                    const current = Number(localStorage.getItem(failKey) || '0') + 1;
                    localStorage.setItem(failKey, String(current));
                    if (current >= 3) {
                        localStorage.setItem(joinLockPrefix + roomId, String(Date.now() + 3600_000));
                    }
                }
                showError('join-error', msg);
            }
        });
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachHandlers);
} else {
    attachHandlers();
}

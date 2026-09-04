#!/usr/bin/env python3
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from flask import Flask, render_template_string, request
from werkzeug.exceptions import RequestEntityTooLarge

# -----------------------------------------------------------------------------
# Flask hardening
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=2048,
    PROPAGATE_EXCEPTIONS=False,
)

# -----------------------------------------------------------------------------
# Rate limit (in-memory): 15 requests per 5 minutes per IP
# -----------------------------------------------------------------------------
RL_WINDOW_SEC = 300
RL_MAX = 15
_rl = defaultdict(lambda: deque())


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def rate_limit_ok() -> bool:
    ip = _client_ip()
    now = time.time()
    q = _rl[ip]
    while q and (now - q[0]) > RL_WINDOW_SEC:
        q.popleft()
    if len(q) >= RL_MAX:
        return False
    q.append(now)
    return True


# -----------------------------------------------------------------------------
# STRICT Validators
# -----------------------------------------------------------------------------
# Telegram bot token: <5-20 digits>:<35 chars [A-Za-z0-9_-]>
TELEGRAM_TOKEN_RE = re.compile(r"^\d{5,20}:[A-Za-z0-9_-]{35}$")


def validate_telegram_token_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    return bool(TELEGRAM_TOKEN_RE.fullmatch(raw))


# Telegram user ID: digits 1-20 (positive only)
TELEGRAM_USER_ID_RE = re.compile(r"^\d{1,20}$")


def validate_telegram_user_id_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    return bool(TELEGRAM_USER_ID_RE.fullmatch(raw))


# Telegram chat ID: optional leading '-', then digits 1-20 (for groups/channels)
TELEGRAM_CHAT_ID_RE = re.compile(r"^-?\d{1,20}$")


def validate_telegram_chat_id_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    return bool(TELEGRAM_CHAT_ID_RE.fullmatch(raw))


# Discord webhook URL strict
DISCORD_ALLOWED_HOSTS = {
    "discord.com",
    "ptb.discord.com",
    "canary.discord.com",
    "discordapp.com",
}
DISCORD_WEBHOOK_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{30,200}$")


def validate_discord_webhook_url_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    if len(raw) > 300:
        return False
    try:
        u = urlsplit(raw)
    except Exception:
        return False
    if u.scheme != "https":
        return False
    if not u.hostname or u.hostname.lower() not in DISCORD_ALLOWED_HOSTS:
        return False
    if u.port is not None or u.username is not None or u.password is not None:
        return False
    if u.query or u.fragment:
        return False
    parts = [p for p in u.path.split("/") if p]
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "webhooks":
        _, _, wid, wtoken = parts
    elif len(parts) == 5 and parts[0] == "api" and parts[1].startswith("v") and parts[2] == "webhooks":
        _, _, _, wid, wtoken = parts
    else:
        return False
    if not wid.isdigit() or not (16 <= len(wid) <= 25):
        return False
    return bool(DISCORD_WEBHOOK_TOKEN_RE.fullmatch(wtoken))


# Discord bot token: three base64url segments
DISCORD_BOT_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9_-]{20,120}\.[A-Za-z0-9_-]{6,12}\.[A-Za-z0-9_-]{20,200}$"
)


def validate_discord_bot_token_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    if not (50 <= len(raw) <= 300):
        return False
    return bool(DISCORD_BOT_TOKEN_RE.fullmatch(raw))


# Optional guild ids: comma-separated snowflakes (digits only)
GUILD_IDS_RE = re.compile(r"^\d{16,25}(,\d{16,25}){0,4}$")


def parse_guild_ids_strict(raw: str | None) -> list[str]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, str):
        return []
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return []
    if "\x00" in raw:
        return []
    if not GUILD_IDS_RE.fullmatch(raw):
        return []
    return raw.split(",")


# Slack webhook URL: https://hooks.slack.com/services/T[0-9A-Z]+/B[0-9A-Z]+/[A-Za-z0-9]+
SLACK_WEBHOOK_RE = re.compile(
    r"^https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[A-Za-z0-9]+$"
)


def validate_slack_webhook_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    return bool(SLACK_WEBHOOK_RE.fullmatch(raw))


# Slack bot token: xoxb- followed by alphanumeric and underscore, 20-80 chars
SLACK_BOT_TOKEN_RE = re.compile(r"^xoxb-[A-Za-z0-9_-]{20,80}$")


def validate_slack_bot_token_strict(raw: str) -> bool:
    if raw is None or not isinstance(raw, str):
        return False
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return False
    if "\x00" in raw:
        return False
    return bool(SLACK_BOT_TOKEN_RE.fullmatch(raw))


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------
def unix_to_utc_str(ts: int | None) -> str:
    if not ts:
        return "unknown time"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# -----------------------------------------------------------------------------
# Telegram logic
# -----------------------------------------------------------------------------
def tg_call_api(method: str, token: str, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except requests.exceptions.RequestException as e:
        return False, None, f"Network error: {type(e).__name__}"
    except ValueError:
        return False, None, "Non-JSON response from Telegram API"
    if not isinstance(data, dict):
        return False, None, "Malformed response"
    if data.get("ok") is True:
        return True, data.get("result"), None
    desc = data.get("description") or "Telegram API returned ok=false"
    code = data.get("error_code")
    if code:
        desc = f"{code}: {desc}"
    return False, None, desc


def tg_get_chat_admins(token: str, chat_id: int):
    ok, res, _ = tg_call_api("getChatAdministrators", token, {"chat_id": chat_id})
    return res if ok and res else []


def tg_get_chat_members_count(token: str, chat_id: int):
    ok, res, _ = tg_call_api("getChatMembersCount", token, {"chat_id": chat_id})
    return res if ok else None


def tg_get_chat_member(token: str, chat_id: int, user_id: int):
    ok, res, _ = tg_call_api("getChatMember", token, {"chat_id": chat_id, "user_id": user_id})
    return res if ok else None


def telegram_check(token: str) -> dict:
    ok, bot_info, err = tg_call_api("getMe", token)
    if not ok:
        return {"ok": False, "platform": "telegram", "error": f"getMe failed: {err}"}

    bot_id = bot_info.get("id")
    bot_username = bot_info.get("username", "unknown")

    wh_ok, webhook_info, wh_err = tg_call_api("getWebhookInfo", token)
    webhook = webhook_info if wh_ok else {"error": wh_err}

    updates_ok, updates, updates_err = tg_call_api(
        "getUpdates",
        token,
        params={
            "timeout": 0,
            "limit": 100,
            "allowed_updates": ["message", "channel_post", "my_chat_member", "edited_message"],
        },
    )

    if not updates_ok:
        return {
            "ok": True,
            "platform": "telegram",
            "bot": {
                "username": bot_username,
                "id": bot_id,
                "can_join_groups": bool(bot_info.get("can_join_groups")),
                "privacy_mode": bool(bot_info.get("can_read_all_group_messages", False)),
            },
            "webhook": webhook,
            "groups": [],
            "private_chats": [],
            "possible_owner_ids": [],
            "recent_messages": [],
            "notes": [
                f"getUpdates failed: {updates_err}",
                "If webhook url is set (non-empty), polling via getUpdates will not work until webhook is removed.",
                "Telegram does not offer an API to enumerate all chats; chats are discovered only from updates.",
            ],
        }

    if not updates:
        return {
            "ok": True,
            "platform": "telegram",
            "bot": {
                "username": bot_username,
                "id": bot_id,
                "can_join_groups": bool(bot_info.get("can_join_groups")),
                "privacy_mode": bool(bot_info.get("can_read_all_group_messages", False)),
            },
            "webhook": webhook,
            "groups": [],
            "private_chats": [],
            "possible_owner_ids": [],
            "recent_messages": [],
            "notes": [
                "No updates returned by getUpdates.",
                "This usually means the bot has not received any recent messages/events.",
                "Telegram does not offer an API to enumerate all chats; chats are discovered only from updates.",
            ],
        }

    groups = {}
    private_chats = {}
    messages = []
    possible_owners = set()

    for upd in updates:
        chat = None
        msg_text = None
        sender = None
        date = None

        if "message" in upd:
            msg = upd["message"]
            chat = msg.get("chat")
            msg_text = msg.get("text") or msg.get("caption") or "[non-text message]"
            sender = msg.get("from", {}) or {}
            date = msg.get("date")
        elif "edited_message" in upd:
            msg = upd["edited_message"]
            chat = msg.get("chat")
            msg_text = msg.get("text") or msg.get("caption") or "[edited non-text]"
            sender = msg.get("from", {}) or {}
            date = msg.get("date")
        elif "my_chat_member" in upd:
            mcm = upd["my_chat_member"]
            chat = mcm.get("chat")
            old_status = (mcm.get("old_chat_member") or {}).get("status")
            new_status = (mcm.get("new_chat_member") or {}).get("status")
            msg_text = f"[bot status changed: {old_status} -> {new_status}]"
            sender = mcm.get("from", {}) or {}
            date = mcm.get("date")
            if new_status in ["member", "administrator"] and old_status in ["left", "kicked"]:
                adder_id = sender.get("id")
                if adder_id:
                    possible_owners.add(adder_id)
        else:
            continue

        if not chat:
            continue

        chat_id = chat.get("id")
        chat_type = chat.get("type", "unknown")
        title = chat.get("title") or (f"{chat.get('first_name','')} {chat.get('last_name','')}".strip())

        if chat_type in ["group", "supergroup"]:
            groups[chat_id] = title or f"Group ID {chat_id}"
        elif chat_type == "private":
            name = (
                f"{sender.get('first_name','')} {sender.get('last_name','')}".strip()
                or sender.get("username", "Unknown")
            )
            private_chats[chat_id] = name

        messages.append(
            {
                "date": date,
                "date_str": unix_to_utc_str(date),
                "chat": f"{chat_type} - {title or chat_id}",
                "from": (
                    f"{sender.get('first_name','')} {sender.get('last_name','')}".strip()
                    or sender.get("username", "System")
                ),
                "text": msg_text,
            }
        )

    group_results = []
    for gid, gname in groups.items():
        admins = tg_get_chat_admins(token, gid)
        admin_summ = []
        for admin in admins:
            user = admin.get("user", {}) or {}
            status = admin.get("status")
            if status == "creator" and user.get("id"):
                possible_owners.add(user["id"])
            admin_summ.append(
                {
                    "id": user.get("id"),
                    "name": (f"{user.get('first_name','')} {user.get('last_name','')}".strip() or "unknown"),
                    "username": user.get("username"),
                    "status": status,
                }
            )

        member_count = tg_get_chat_members_count(token, gid)
        bot_member = tg_get_chat_member(token, gid, bot_id) if bot_id else None
        bot_role = bot_member.get("status") if isinstance(bot_member, dict) else None

        group_results.append(
            {
                "id": gid,
                "name": gname,
                "member_count": member_count,
                "bot_role": bot_role,
                "admins": admin_summ,
            }
        )

    return {
        "ok": True,
        "platform": "telegram",
        "bot": {
            "username": bot_username,
            "id": bot_id,
            "can_join_groups": bool(bot_info.get("can_join_groups")),
            "privacy_mode": bool(bot_info.get("can_read_all_group_messages", False)),
        },
        "webhook": webhook,
        "groups": group_results,
        "private_chats": [{"id": cid, "name": name} for cid, name in private_chats.items()],
        "possible_owner_ids": sorted(possible_owners),
        "recent_messages": messages[-20:],
        "notes": [
            "Chats/groups are discovered from updates only (Telegram provides no 'list chats' endpoint).",
            "If you expect data, ensure the bot received messages/events recently and webhook url is empty.",
        ],
    }


def telegram_user_check(bot_token: str, user_id: str) -> dict:
    """Look up a specific user by ID using a bot token."""
    ok, bot_info, err = tg_call_api("getMe", bot_token)
    if not ok:
        return {"ok": False, "platform": "telegram_user", "error": f"getMe failed: {err}"}

    ok_chat, chat_info, err_chat = tg_call_api("getChat", bot_token, {"chat_id": user_id})
    if not ok_chat:
        return {
            "ok": True,
            "platform": "telegram_user",
            "bot": {"id": bot_info.get("id"), "username": bot_info.get("username")},
            "user": None,
            "notes": [
                f"Could not retrieve info for user {user_id}: {err_chat}",
                "The bot may not have interacted with this user, or the ID is invalid.",
                "Telegram only allows retrieving users that the bot has seen (e.g., in groups or private chats).",
            ],
        }

    user_data = {
        "id": chat_info.get("id"),
        "type": chat_info.get("type"),
        "first_name": chat_info.get("first_name"),
        "last_name": chat_info.get("last_name"),
        "username": chat_info.get("username"),
        "is_bot": chat_info.get("is_bot", False),
        "bio": chat_info.get("bio"),
        "can_join_groups": chat_info.get("can_join_groups"),
        "can_read_all_group_messages": chat_info.get("can_read_all_group_messages"),
        "supports_inline_queries": chat_info.get("supports_inline_queries"),
    }

    return {
        "ok": True,
        "platform": "telegram_user",
        "bot": {"id": bot_info.get("id"), "username": bot_info.get("username")},
        "user": user_data,
        "notes": [
            "The user info was retrieved via getChat, which works only if the bot has seen this user.",
            "If the user is a bot, the 'is_bot' field will be true (if returned).",
        ],
    }


def telegram_chat_check(bot_token: str, chat_id: str) -> dict:
    """Get detailed info about a specific chat (user, group, channel) using a bot token."""
    ok, bot_info, err = tg_call_api("getMe", bot_token)
    if not ok:
        return {"ok": False, "platform": "telegram_chat", "error": f"getMe failed: {err}"}

    # Get chat info
    ok_chat, chat_info, err_chat = tg_call_api("getChat", bot_token, {"chat_id": chat_id})
    if not ok_chat:
        return {
            "ok": False,
            "platform": "telegram_chat",
            "error": f"getChat failed: {err_chat}",
            "notes": [
                "Make sure the bot has interacted with this chat (e.g., is a member).",
                "For groups, the bot must be added; for users, the bot must have seen them.",
            ],
        }

    # Basic chat info
    chat_type = chat_info.get("type")
    chat_title = chat_info.get("title") or f"{chat_info.get('first_name','')} {chat_info.get('last_name','')}".strip()
    result = {
        "ok": True,
        "platform": "telegram_chat",
        "bot": {"id": bot_info.get("id"), "username": bot_info.get("username")},
        "chat": {
            "id": chat_info.get("id"),
            "type": chat_type,
            "title": chat_title,
            "username": chat_info.get("username"),
            "description": chat_info.get("description"),
            "invite_link": chat_info.get("invite_link"),
            "pinned_message": chat_info.get("pinned_message"),
            "permissions": chat_info.get("permissions"),
            "slow_mode_delay": chat_info.get("slow_mode_delay"),
            "message_auto_delete_time": chat_info.get("message_auto_delete_time"),
            "has_protected_content": chat_info.get("has_protected_content"),
            "sticker_set_name": chat_info.get("sticker_set_name"),
            "can_set_sticker_set": chat_info.get("can_set_sticker_set"),
            "linked_chat_id": chat_info.get("linked_chat_id"),
        },
        "admins": [],
        "member_count": None,
        "bot_role": None,
        "notes": [],
    }

    # For groups/supergroups, get admins, member count, and bot role
    if chat_type in ["group", "supergroup"]:
        # Get admins
        admins = tg_get_chat_admins(bot_token, int(chat_id))
        if admins:
            for admin in admins:
                user = admin.get("user", {}) or {}
                result["admins"].append({
                    "id": user.get("id"),
                    "name": (f"{user.get('first_name','')} {user.get('last_name','')}".strip() or "unknown"),
                    "username": user.get("username"),
                    "status": admin.get("status"),
                    "is_anonymous": admin.get("is_anonymous"),
                    "can_be_edited": admin.get("can_be_edited"),
                })

        # Member count
        count = tg_get_chat_members_count(bot_token, int(chat_id))
        result["member_count"] = count

        # Bot's own member status
        bot_member = tg_get_chat_member(bot_token, int(chat_id), bot_info.get("id"))
        if bot_member:
            result["bot_role"] = bot_member.get("status")
        else:
            result["bot_role"] = "unknown (not member?)"

        result["notes"].append("For groups, admins and member count are included.")
    elif chat_type == "private":
        result["notes"].append("This is a private chat (user). No admin/member data available.")
    elif chat_type == "channel":
        # Channels may have admins too? Actually getChatAdministrators works for channels as well.
        admins = tg_get_chat_admins(bot_token, int(chat_id))
        if admins:
            for admin in admins:
                user = admin.get("user", {}) or {}
                result["admins"].append({
                    "id": user.get("id"),
                    "name": (f"{user.get('first_name','')} {user.get('last_name','')}".strip() or "unknown"),
                    "username": user.get("username"),
                    "status": admin.get("status"),
                })
        result["notes"].append("Channel admins are listed if available.")
    else:
        result["notes"].append(f"Unknown chat type: {chat_type}")

    return result


# -----------------------------------------------------------------------------
# Discord webhook check (GET-only)
# -----------------------------------------------------------------------------
def discord_webhook_check(webhook_url: str) -> dict:
    try:
        r = requests.get(webhook_url, timeout=10)
    except requests.exceptions.RequestException as e:
        return {"ok": False, "platform": "discord_webhook", "error": f"Network error: {type(e).__name__}"}

    if r.status_code != 200:
        return {"ok": False, "platform": "discord_webhook", "error": f"Discord returned HTTP {r.status_code}"}

    try:
        data = r.json()
    except ValueError:
        return {"ok": False, "platform": "discord_webhook", "error": "Non-JSON response from Discord"}

    return {
        "ok": True,
        "platform": "discord_webhook",
        "webhook": {
            "id": data.get("id"),
            "name": data.get("name"),
            "type": data.get("type"),
            "guild_id": data.get("guild_id"),
            "channel_id": data.get("channel_id"),
            "application_id": data.get("application_id"),
        },
        "notes": [
            "Webhook URLs are not bot identities; they cannot enumerate guild members/admins/messages.",
            "This check performs a GET only; it does not send messages.",
        ],
    }


# -----------------------------------------------------------------------------
# Discord bot token check
# -----------------------------------------------------------------------------
DISCORD_API_BASE = "https://discord.com/api/v10"
ADMINISTRATOR_BIT = 0x00000008


def dc_call(method: str, path: str, bot_token: str, params=None):
    url = f"{DISCORD_API_BASE}{path}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "credential-checker/1.0",
    }
    try:
        r = requests.request(method, url, headers=headers, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        return False, None, f"Network error: {type(e).__name__}"

    if r.status_code < 200 or r.status_code >= 300:
        try:
            j = r.json()
            msg = j.get("message")
            code = j.get("code")
            if msg and code:
                return False, None, f"HTTP {r.status_code}: {code} {msg}"
            if msg:
                return False, None, f"HTTP {r.status_code}: {msg}"
        except ValueError:
            pass
        return False, None, f"HTTP {r.status_code}"

    try:
        return True, r.json() if r.content else None, None
    except ValueError:
        return False, None, "Non-JSON response from Discord API"


def discord_bot_check(bot_token: str, guild_ids: list[str]) -> dict:
    ok, me, err = dc_call("GET", "/users/@me", bot_token)
    if not ok:
        return {"ok": False, "platform": "discord_bot", "error": f"/users/@me failed: {err}"}

    bot_id = me.get("id")
    username = f"{me.get('username','unknown')}#{me.get('discriminator','0000')}"
    is_bot = bool(me.get("bot", True))

    result = {
        "ok": True,
        "platform": "discord_bot",
        "bot": {"id": bot_id, "username": username, "bot_flag": is_bot},
        "guilds": [],
        "notes": [],
    }

    if not guild_ids:
        result["notes"].append(
            "Discord does not provide a REST endpoint to list all guilds a bot is in; provide guild_id(s) to query."
        )
        result["notes"].append("You can supply up to 5 guild ids, comma-separated, digits only, no spaces.")
        return result

    for gid in guild_ids:
        g_entry = {"id": gid, "ok": False}

        ok_g, g, err_g = dc_call("GET", f"/guilds/{gid}", bot_token, params={"with_counts": "true"})
        if not ok_g:
            g_entry["error"] = f"get guild failed: {err_g}"
            result["guilds"].append(g_entry)
            continue

        ok_roles, roles, err_roles = dc_call("GET", f"/guilds/{gid}/roles", bot_token)
        admin_roles = []
        if ok_roles and isinstance(roles, list):
            for r in roles:
                try:
                    perms = int(r.get("permissions", "0"))
                except ValueError:
                    perms = 0
                if perms & ADMINISTRATOR_BIT:
                    admin_roles.append({"id": r.get("id"), "name": r.get("name")})
        else:
            g_entry["roles_error"] = err_roles

        ok_ch, channels, err_ch = dc_call("GET", f"/guilds/{gid}/channels", bot_token)
        chan_summ = []
        if ok_ch and isinstance(channels, list):
            for ch in channels[:30]:
                chan_summ.append({"id": ch.get("id"), "name": ch.get("name"), "type": ch.get("type")})
        else:
            g_entry["channels_error"] = err_ch

        bot_member = None
        if bot_id:
            ok_m, m, err_m = dc_call("GET", f"/guilds/{gid}/members/{bot_id}", bot_token)
            if ok_m and isinstance(m, dict):
                bot_member = {
                    "nick": m.get("nick"),
                    "roles_count": len(m.get("roles") or []),
                    "joined_at": m.get("joined_at"),
                }
            else:
                g_entry["bot_member_error"] = err_m

        g_entry.update(
            {
                "ok": True,
                "name": g.get("name"),
                "owner_id": g.get("owner_id"),
                "approximate_member_count": g.get("approximate_member_count"),
                "approximate_presence_count": g.get("approximate_presence_count"),
                "admin_roles": admin_roles[:20],
                "channels": chan_summ,
                "bot_member": bot_member,
            }
        )
        result["guilds"].append(g_entry)

    result["notes"].append(
        "Member/admin enumeration beyond roles/channels requires additional permissions and sometimes privileged intents."
    )
    return result


# -----------------------------------------------------------------------------
# Slack logic
# -----------------------------------------------------------------------------
def slack_webhook_check(webhook_url: str) -> dict:
    return {
        "ok": True,
        "platform": "slack_webhook",
        "webhook_url": webhook_url,
        "notes": [
            "Webhook URL format validated. Slack does not support GET requests on webhooks.",
            "To test, a POST would be required (which may send a message). This check does not send any message.",
        ],
    }


def slack_bot_check(bot_token: str) -> dict:
    url = "https://slack.com/api/auth.test"
    headers = {"Authorization": f"Bearer {bot_token}"}
    try:
        r = requests.post(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        return {"ok": False, "platform": "slack_bot", "error": f"Network error: {type(e).__name__}"}

    if r.status_code != 200:
        return {"ok": False, "platform": "slack_bot", "error": f"Slack returned HTTP {r.status_code}"}

    try:
        data = r.json()
    except ValueError:
        return {"ok": False, "platform": "slack_bot", "error": "Non-JSON response"}

    if data.get("ok") is not True:
        error = data.get("error", "unknown error")
        return {"ok": False, "platform": "slack_bot", "error": f"Slack API error: {error}"}

    return {
        "ok": True,
        "platform": "slack_bot",
        "bot": {
            "user_id": data.get("user_id"),
            "team_id": data.get("team_id"),
            "team": data.get("team"),
            "url": data.get("url"),
            "bot_id": data.get("bot_id"),
            "app_id": data.get("app_id"),
        },
        "notes": [
            "Bot token validated via auth.test. This token can be used to call Slack APIs.",
            "Scopes and permissions are not checked; you may need additional scopes for specific operations.",
        ],
    }


# -----------------------------------------------------------------------------
# UI (black & white terminal) with conditional fields
# -----------------------------------------------------------------------------
PAGE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Credential Checker</title>
  <style>
    :root{--bg:#000;--fg:#fff;--dim:#cfcfcf;--border:#fff;--mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;}
    html,body{height:100%;}
    body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--mono);font-size:14px;}
    .wrap{max-width:980px;margin:0 auto;padding:22px 16px 40px;}
    h1{margin:0 0 14px 0;font-size:16px;font-weight:700;}
    .panel{border:1px solid var(--border); padding:14px;}
    .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
    select,input,button{
      padding:8px 10px;border:1px solid var(--border);background:#000;color:#fff;
      font-family:var(--mono);font-size:14px;
    }
    input{flex:1 1 420px;min-width:260px;outline:none;}
    .small{flex:0 1 260px;min-width:220px;}
    button{cursor:pointer;}
    button:hover{background:#111;}
    .help{margin-top:10px;color:var(--dim); line-height:1.4;}
    .alert{margin-top:12px;border:1px solid var(--border);padding:10px;white-space:pre-wrap;}
    .section{margin-top:14px;}
    .title{color:var(--dim); margin-bottom:6px;}
    pre{
      margin:8px 0 0;border:1px solid var(--border);padding:10px;background:#000;color:#fff;
      overflow:auto;white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.35;
    }
    table{width:100%;border-collapse:collapse;margin-top:6px;}
    td,th{border:1px solid var(--border);padding:6px 8px;vertical-align:top;}
    th{color:var(--dim); font-weight:700;}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>credential checker</h1>

    <div class="panel">
      <form method="post" action="/check" autocomplete="off">
        <div class="row">
          <select name="platform" aria-label="platform">
            <option value="telegram">telegram bot token</option>
            <option value="telegram_user">telegram user ID (with bot token)</option>
            <option value="telegram_chat">telegram chat ID (with bot token)</option>
            <option value="discord_webhook">discord webhook</option>
            <option value="discord_bot">discord bot token</option>
            <option value="slack_webhook">slack webhook</option>
            <option value="slack_bot">slack bot token</option>
          </select>

          <input name="secret" type="password" placeholder="token / webhook url" required />
          <button type="submit">search</button>
        </div>

        <!-- Extra fields, shown conditionally -->
        <div class="row" id="extraRow" style="margin-top:10px; display:none;">
          <input class="small" id="extraInput" name="extra" type="text"
                 placeholder="user ID / chat ID / guild IDs" />
        </div>

        <div class="help" id="helpText">
          Strict allow-list validation. On mismatch: request rejected, no external calls.
        </div>
      </form>

      {% if alert %}
        <div class="alert">{{alert}}</div>
      {% endif %}

      {% if result and result.ok and result.platform == "telegram" %}
        <div class="section"><div class="title">telegram bot</div>
          <pre>@{{result.bot.username}}  id={{result.bot.id}}
can_join_groups={{result.bot.can_join_groups}}
privacy_mode(can_read_all_group_messages)={{result.bot.privacy_mode}}</pre>
        </div>
        <div class="section"><div class="title">webhook info</div><pre>{{result.webhook | tojson}}</pre></div>

        <div class="section">
          <div class="title">groups ({{result.groups|length}})</div>
          {% if result.groups %}
          <table>
            <tr><th>name</th><th>id</th><th>members</th><th>bot role</th><th>admins</th></tr>
            {% for g in result.groups %}
              <tr><td>{{g.name}}</td><td>{{g.id}}</td><td>{{g.member_count}}</td><td>{{g.bot_role}}</td><td>{{g.admins|length}}</td></tr>
            {% endfor %}
          </table>
          {% else %}<pre>(none discovered from updates)</pre>{% endif %}
        </div>

        <div class="section"><div class="title">recent messages (last {{result.recent_messages|length}})</div>
          <pre>{% for m in result.recent_messages %}{{m.date_str}} | {{m.chat}} | {{m.from}}: {{m.text}}
{% endfor %}</pre>
        </div>

        <div class="section"><div class="title">notes</div>
          <pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre>
        </div>

      {% elif result and result.ok and result.platform == "telegram_user" %}
        <div class="section"><div class="title">telegram user lookup</div>
          <pre>bot used: @{{result.bot.username}} (id={{result.bot.id}})</pre>
          <div class="title">user info</div>
          {% if result.user %}
            <pre>id: {{result.user.id}}
type: {{result.user.type}}
first_name: {{result.user.first_name}}
last_name: {{result.user.last_name}}
username: {{result.user.username}}
is_bot: {{result.user.is_bot}}
bio: {{result.user.bio}}
can_join_groups: {{result.user.can_join_groups}}
can_read_all_group_messages: {{result.user.can_read_all_group_messages}}
supports_inline_queries: {{result.user.supports_inline_queries}}</pre>
          {% else %}
            <pre>User info not available (see notes).</pre>
          {% endif %}
        </div>
        <div class="section"><div class="title">notes</div><pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre></div>

      {% elif result and result.ok and result.platform == "telegram_chat" %}
        <div class="section"><div class="title">telegram chat info</div>
          <pre>bot used: @{{result.bot.username}} (id={{result.bot.id}})</pre>
          <div class="title">chat details</div>
          <pre>id: {{result.chat.id}}
type: {{result.chat.type}}
title: {{result.chat.title}}
username: {{result.chat.username}}
description: {{result.chat.description}}
invite_link: {{result.chat.invite_link}}
slow_mode_delay: {{result.chat.slow_mode_delay}}
message_auto_delete_time: {{result.chat.message_auto_delete_time}}
has_protected_content: {{result.chat.has_protected_content}}
sticker_set_name: {{result.chat.sticker_set_name}}
can_set_sticker_set: {{result.chat.can_set_sticker_set}}
linked_chat_id: {{result.chat.linked_chat_id}}
member_count: {{result.member_count}}
bot_role: {{result.bot_role}}</pre>
          {% if result.admins %}
          <div class="title">admins ({{result.admins|length}})</div>
          <pre>{% for a in result.admins %}{{a.status}}: {{a.name}} (@{{a.username}}) id={{a.id}}
{% endfor %}</pre>
          {% endif %}
        </div>
        <div class="section"><div class="title">notes</div><pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre></div>

      {% elif result and result.ok and result.platform == "discord_webhook" %}
        <div class="section"><div class="title">discord webhook</div><pre>{{result.webhook | tojson}}</pre></div>
        <div class="section"><div class="title">notes</div><pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre></div>

      {% elif result and result.ok and result.platform == "discord_bot" %}
        <div class="section"><div class="title">discord bot</div>
          <pre>id={{result.bot.id}}
username={{result.bot.username}}
bot_flag={{result.bot.bot_flag}}</pre>
        </div>

        <div class="section">
          <div class="title">guilds ({{result.guilds|length}})</div>
          {% if result.guilds %}
            {% for g in result.guilds %}
              <pre>guild_id={{g.id}}
ok={{g.ok}}
{% if g.ok %}
name={{g.name}}
owner_id={{g.owner_id}}
approx_members={{g.approximate_member_count}}
approx_online={{g.approximate_presence_count}}
admin_roles={{g.admin_roles | tojson}}
channels(sample,max30)={{g.channels | tojson}}
bot_member={{g.bot_member | tojson}}
{% else %}
error={{g.error}}
{% endif %}
{% if g.roles_error %}roles_error={{g.roles_error}}{% endif %}
{% if g.channels_error %}channels_error={{g.channels_error}}{% endif %}
{% if g.bot_member_error %}bot_member_error={{g.bot_member_error}}{% endif %}</pre>
            {% endfor %}
          {% else %}
            <pre>(no guild ids provided)</pre>
          {% endif %}
        </div>

        <div class="section"><div class="title">notes</div><pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre></div>

      {% elif result and result.ok and result.platform == "slack_webhook" %}
        <div class="section"><div class="title">slack webhook</div><pre>URL: {{result.webhook_url}}</pre></div>
        <div class="section"><div class="title">notes</div><pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre></div>

      {% elif result and result.ok and result.platform == "slack_bot" %}
        <div class="section"><div class="title">slack bot</div>
          <pre>user_id: {{result.bot.user_id}}
team_id: {{result.bot.team_id}}
team: {{result.bot.team}}
url: {{result.bot.url}}
bot_id: {{result.bot.bot_id}}
app_id: {{result.bot.app_id}}</pre>
        </div>
        <div class="section"><div class="title">notes</div><pre>{% for n in result.notes %}- {{n}}
{% endfor %}</pre></div>

      {% elif result and not result.ok %}
        <div class="alert">{{result.error}}</div>
      {% endif %}
    </div>
  </div>

<script>
(function(){
  var platformSel = document.querySelector('select[name="platform"]');
  var extraRow = document.getElementById('extraRow');
  var extraInput = document.getElementById('extraInput');
  var helpText = document.getElementById('helpText');

  function syncExtraField(){
    var platform = platformSel ? platformSel.value : '';
    // Show extra field for telegram_user, telegram_chat, discord_bot
    if (platform === 'telegram_user') {
      extraRow.style.display = '';
      extraInput.placeholder = 'telegram user ID (digits only)';
      extraInput.disabled = false;
      helpText.textContent = "Provide a Telegram bot token and the user ID to look up.";
    } else if (platform === 'telegram_chat') {
      extraRow.style.display = '';
      extraInput.placeholder = 'chat ID (e.g., -1001234567890)';
      extraInput.disabled = false;
      helpText.textContent = "Provide a Telegram bot token and a chat ID (user, group, or channel).";
    } else if (platform === 'discord_bot') {
      extraRow.style.display = '';
      extraInput.placeholder = 'guild IDs (optional, comma-separated)';
      extraInput.disabled = false;
      helpText.textContent = "Provide Discord bot token and optional guild IDs (digits, comma-separated, max 5).";
    } else {
      extraRow.style.display = 'none';
      extraInput.disabled = true;
      extraInput.value = '';
      helpText.textContent = "Strict allow-list validation. On mismatch: request rejected, no external calls.";
    }
  }

  if (platformSel) {
    platformSel.addEventListener('change', syncExtraField);
    syncExtraField();
  }
})();
</script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Graceful error handlers
# -----------------------------------------------------------------------------
@app.errorhandler(RequestEntityTooLarge)
def handle_413(e):
    return (
        render_template_string(PAGE, alert="request too large (413)\ninput rejected without processing.", result=None),
        413,
    )


@app.errorhandler(400)
def handle_400(e):
    return render_template_string(PAGE, alert="bad request (400)", result=None), 400


@app.errorhandler(415)
def handle_415(e):
    return render_template_string(PAGE, alert="unsupported content-type (415)", result=None), 415


@app.errorhandler(429)
def handle_429(e):
    return render_template_string(PAGE, alert="rate limit exceeded (429)", result=None), 429


# -----------------------------------------------------------------------------
@app.before_request
def _preflight():
    if not rate_limit_ok():
        return render_template_string(PAGE, alert="rate limit exceeded (429)", result=None), 429

    if request.path == "/check" and request.method == "POST":
        ct = request.content_type or ""
        if not ct.startswith("application/x-www-form-urlencoded"):
            return render_template_string(PAGE, alert="unsupported content-type (415)", result=None), 415


@app.get("/")
def index():
    return render_template_string(PAGE, alert=None, result=None)


@app.post("/check")
def check():
    platform_vals = request.form.getlist("platform")
    secret_vals = request.form.getlist("secret")
    extra_vals = request.form.getlist("extra")  # optional extra field

    if len(platform_vals) != 1 or len(secret_vals) != 1:
        return render_template_string(PAGE, alert="invalid request (400)", result=None), 400

    if len(extra_vals) == 0:
        extra_raw = ""
    elif len(extra_vals) == 1:
        extra_raw = extra_vals[0]
    else:
        return render_template_string(PAGE, alert="invalid request (400)", result=None), 400

    platform = platform_vals[0]
    raw = secret_vals[0]

    # -----------------------------------------------------------------
    # Telegram bot token
    # -----------------------------------------------------------------
    if platform == "telegram":
        if not validate_telegram_token_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid telegram token format (400)\nexpected: <5-20 digits>:<35 chars in [A-Za-z0-9_-]>",
                    result=None,
                ),
                400,
            )
        result = telegram_check(raw)
        return render_template_string(PAGE, alert=None, result=result), 200

    # -----------------------------------------------------------------
    # Telegram user ID (with bot token)
    # -----------------------------------------------------------------
    if platform == "telegram_user":
        if not validate_telegram_token_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid telegram bot token format (400)\nexpected: <5-20 digits>:<35 chars in [A-Za-z0-9_-]>",
                    result=None,
                ),
                400,
            )
        if not validate_telegram_user_id_strict(extra_raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid telegram user ID (400)\nexpected: digits only, 1-20 characters",
                    result=None,
                ),
                400,
            )
        result = telegram_user_check(raw, extra_raw)
        return render_template_string(PAGE, alert=None, result=result), 200

    # -----------------------------------------------------------------
    # Telegram chat ID (with bot token) - NEW
    # -----------------------------------------------------------------
    if platform == "telegram_chat":
        if not validate_telegram_token_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid telegram bot token format (400)\nexpected: <5-20 digits>:<35 chars in [A-Za-z0-9_-]>",
                    result=None,
                ),
                400,
            )
        if not validate_telegram_chat_id_strict(extra_raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid chat ID (400)\nexpected: digits with optional leading minus, 1-20 characters",
                    result=None,
                ),
                400,
            )
        result = telegram_chat_check(raw, extra_raw)
        return render_template_string(PAGE, alert=None, result=result), 200

    # -----------------------------------------------------------------
    # Discord webhook
    # -----------------------------------------------------------------
    if platform == "discord_webhook":
        if not validate_discord_webhook_url_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert=(
                        "invalid discord webhook url (400)\n"
                        "expected: https://discord.com/api/webhooks/<id>/<token>\n"
                        "or:       https://discord.com/api/vN/webhooks/<id>/<token>\n"
                        "no query/fragment/port/credentials allowed."
                    ),
                    result=None,
                ),
                400,
            )
        result = discord_webhook_check(raw)
        return render_template_string(PAGE, alert=None, result=result), 200

    # -----------------------------------------------------------------
    # Discord bot token
    # -----------------------------------------------------------------
    if platform == "discord_bot":
        if not validate_discord_bot_token_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert=(
                        "invalid discord bot token format (400)\n"
                        "expected: <base64url>.<base64url>.<base64url> (ascii, no spaces)"
                    ),
                    result=None,
                ),
                400,
            )

        # extra_raw contains guild ids (optional)
        guild_ids = parse_guild_ids_strict(extra_raw)
        if extra_raw != "" and not guild_ids:
            return (
                render_template_string(
                    PAGE,
                    alert="invalid guild_ids (400)\nexpected digits-only CSV, up to 5 ids, no spaces.",
                    result=None,
                ),
                400,
            )

        result = discord_bot_check(raw, guild_ids)
        return render_template_string(PAGE, alert=None, result=result), 200

    # -----------------------------------------------------------------
    # Slack webhook
    # -----------------------------------------------------------------
    if platform == "slack_webhook":
        if not validate_slack_webhook_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid slack webhook url (400)\nexpected: https://hooks.slack.com/services/T.../B.../...",
                    result=None,
                ),
                400,
            )
        result = slack_webhook_check(raw)
        return render_template_string(PAGE, alert=None, result=result), 200

    # -----------------------------------------------------------------
    # Slack bot token
    # -----------------------------------------------------------------
    if platform == "slack_bot":
        if not validate_slack_bot_token_strict(raw):
            return (
                render_template_string(
                    PAGE,
                    alert="invalid slack bot token (400)\nexpected: xoxb- followed by 20-80 alphanumeric/underscore",
                    result=None,
                ),
                400,
            )
        result = slack_bot_check(raw)
        return render_template_string(PAGE, alert=None, result=result), 200

    return render_template_string(PAGE, alert="unknown platform (400)", result=None), 400


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
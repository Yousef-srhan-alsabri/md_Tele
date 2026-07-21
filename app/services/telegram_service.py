import asyncio
import re
import secrets
from dataclasses import dataclass
from enum import Enum
from telethon import TelegramClient, functions
from telethon.errors import (
    ChannelsTooMuchError, FloodWaitError, InviteHashExpiredError,
    InviteHashInvalidError, InviteRequestSentError, SessionPasswordNeededError,
    UserAlreadyParticipantError,
)
from telethon.sessions import StringSession
from app.config import get_settings

settings = get_settings()

class JoinKind(str, Enum):
    JOINED = "joined"
    REQUESTED = "requested"
    ALREADY_MEMBER = "already_member"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"

@dataclass
class JoinResult:
    kind: JoinKind
    message: str
    retry_after: int | None = None

_login_clients: dict[str, TelegramClient] = {}
_login_meta: dict[str, dict] = {}
_login_lock = asyncio.Lock()

LINK_RE = re.compile(r"(?:https?://)?(?:t\.me/|telegram\.me/)([a-zA-Z0-9_]+|joinchat/[a-zA-Z0-9_-]+|\+[a-zA-Z0-9_-]+)")

def extract_links(text: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in LINK_RE.findall(text):
        value = raw.strip()
        if not value.startswith(("+", "joinchat/")):
            value = value.lower()
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output

async def begin_login(user_id: int, phone: str) -> str:
    client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()
    sent = await client.send_code_request(phone)
    login_id = secrets.token_urlsafe(24)
    async with _login_lock:
        _login_clients[login_id] = client
        _login_meta[login_id] = {"user_id": user_id, "phone": phone, "phone_code_hash": sent.phone_code_hash}
    return login_id

async def complete_login(user_id: int, login_id: str, code: str, password: str | None = None) -> tuple[str, str]:
    async with _login_lock:
        client = _login_clients.get(login_id)
        meta = _login_meta.get(login_id)
    if not client or not meta or meta["user_id"] != user_id:
        raise ValueError("جلسة تسجيل الدخول منتهية أو غير صالحة")
    try:
        try:
            await client.sign_in(meta["phone"], code, phone_code_hash=meta["phone_code_hash"])
        except SessionPasswordNeededError:
            if not password:
                raise PermissionError("TWO_FACTOR_REQUIRED")
            await client.sign_in(password=password)
        return meta["phone"], StringSession.save(client.session)
    finally:
        if client.is_connected():
            await client.disconnect()
        async with _login_lock:
            _login_clients.pop(login_id, None)
            _login_meta.pop(login_id, None)

async def join_link(session_string: str, link: str) -> JoinResult:
    client = TelegramClient(
        StringSession(session_string), settings.telegram_api_id, settings.telegram_api_hash,
        receive_updates=False, request_retries=2, connection_retries=2,
        flood_sleep_threshold=0,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return JoinResult(JoinKind.FAILED, "جلسة الحساب غير صالحة؛ أعد تسجيل الحساب")
        if link.startswith("joinchat/") or link.startswith("+"):
            invite_hash = link.split("/")[-1].lstrip("+")
            await client(functions.messages.ImportChatInviteRequest(hash=invite_hash))
        else:
            await client(functions.channels.JoinChannelRequest(channel=link))
        return JoinResult(JoinKind.JOINED, "تم الانضمام بنجاح")
    except UserAlreadyParticipantError:
        return JoinResult(JoinKind.ALREADY_MEMBER, "الحساب عضو بالفعل")
    except InviteRequestSentError:
        return JoinResult(JoinKind.REQUESTED, "تم إرسال طلب الانضمام وبانتظار الموافقة")
    except FloodWaitError as exc:
        return JoinResult(JoinKind.RETRY_WAIT, f"Telegram طلب الانتظار {exc.seconds} ثانية", exc.seconds)
    except ChannelsTooMuchError:
        return JoinResult(JoinKind.FAILED, "الحساب بلغ الحد الأقصى للقنوات")
    except (InviteHashExpiredError, InviteHashInvalidError):
        return JoinResult(JoinKind.FAILED, "رابط الدعوة غير صالح أو منتهي")
    except Exception as exc:
        return JoinResult(JoinKind.FAILED, f"فشل التنفيذ: {type(exc).__name__}")
    finally:
        if client.is_connected():
            await client.disconnect()

#!/usr/bin/env python3

from __future__ import annotations

import os
import ssl
import asyncio
import json
from pathlib import Path

import certifi
import aiohttp
from aiohttp import web


# ============================================================
# SSL / CA CONFIGURATION
# ============================================================

CA_BUNDLE = None
SSL_CONTEXT = None

try:
    CA_BUNDLE = certifi.where()

    # Android APK daxilində HTTPS kitabxanalarının
    # certifi CA bundle istifadə etməsini təmin et.
    os.environ["SSL_CERT_FILE"] = CA_BUNDLE
    os.environ["REQUESTS_CA_BUNDLE"] = CA_BUNDLE
    os.environ["CURL_CA_BUNDLE"] = CA_BUNDLE

    SSL_CONTEXT = ssl.create_default_context(cafile=CA_BUNDLE)

    # Təhlükəsizlik:
    # sertifikat yoxlaması AÇIQ qalır.
    SSL_CONTEXT.check_hostname = True
    SSL_CONTEXT.verify_mode = ssl.CERT_REQUIRED

    print(f"[SSL] CA bundle: {CA_BUNDLE}")
    print(f"[SSL] OpenSSL: {ssl.OPENSSL_VERSION}")
    print("[SSL] Certificate verification: ENABLED")

except Exception as exc:
    print(
        "[SSL] CA configuration FAILED:",
        type(exc).__name__,
        str(exc),
    )


def get_ssl_context():
    """
    TikTokLive / aiohttp üçün təhlükəsiz SSL context.
    """
    if SSL_CONTEXT is not None:
        return SSL_CONTEXT

    # certifi qurulmayıbsa belə SSL-i söndürmə.
    return ssl.create_default_context()


# ============================================================
# TIKTOK LIVE
# ============================================================

TIKTOK_AVAILABLE = False
TikTokLiveClient = None

ConnectEvent = (
    DisconnectEvent
    GiftEvent
    LikeEvent
    FollowEvent
) = None

WebDefaults = None

UserOfflineError = (
    UserNotFoundError
    AlreadyConnectedError
) = Exception


try:
    from TikTokLive import TikTokLiveClient

    from TikTokLive.events import (
        ConnectEvent,
        DisconnectEvent,
        GiftEvent,
        LikeEvent,
        FollowEvent,
    )

    from TikTokLive.client.web.web_settings import WebDefaults

    try:
        from TikTokLive.client.errors import (
            UserOfflineError,
            UserNotFoundError,
            AlreadyConnectedError,
        )

    except Exception:

        try:
            from TikTokLive.errors import (
                UserOfflineError,
                UserNotFoundError,
                AlreadyConnectedError,
            )

        except Exception:

            class UserOfflineError(Exception):
                pass

            class UserNotFoundError(Exception):
                pass

            class AlreadyConnectedError(Exception):
                pass

    TIKTOK_AVAILABLE = True
    print("[TikTokLive] IMPORT OK")

except Exception as exc:
    print(
        "[TikTokLive] IMPORT FAILED:",
        type(exc).__name__,
        str(exc),
    )


# ============================================================
# SERVER CONFIG
# ============================================================

HOST = "0.0.0.0"
PORT = 8000

PLAYER_COUNT = 7

ROOT = Path(__file__).resolve().parent

GIFT_POINTS = 1
FOLLOW_POINTS = 2
LIKE_POINTS = 1
LIKE_EVERY = 20


GIFT_MAP = {
    "rose": 0,
    "gül": 0,
    "gul": 0,
    "my first rose": 0,
    "rosa": 0,

    "tiktok": 1,

    "flame heart": 2,
    "flameheart": 2,
    "flame": 2,

    "gg": 3,

    "ice cream cone": 4,
    "ice cream": 4,
    "icecream": 4,
    "dondurma": 4,

    "football": 5,
    "futbol": 5,
    "soccer": 5,
    "soccer ball": 5,

    "heart puff": 6,
    "heartpuff": 6,
}


# ============================================================
# GLOBAL STATE
# ============================================================

clients: set[web.WebSocketResponse] = set()

scores = [0] * PLAYER_COUNT

supporters: dict[str, int] = {}

total_likes = 0
like_points_given = 0

tiktok_client = None

current_user = ""
current_api_key = ""

_connect_task = None


# ============================================================
# WEBSOCKET
# ============================================================

async def broadcast(data: dict) -> None:

    if not clients:
        return

    message = json.dumps(
        data,
        ensure_ascii=False,
    )

    dead = []

    for ws in list(clients):

        try:
            await ws.send_str(message)

        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)


async def broadcast_scores() -> None:

    await broadcast({
        "type": "scores",
        "scores": scores[:],
    })


async def broadcast_top() -> None:

    top = sorted(
        supporters.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    await broadcast({
        "type": "top_supporters",
        "list": [
            {
                "username": u,
                "coins": c,
            }
            for u, c in top
        ],
    })


# ============================================================
# USER / GIFT
# ============================================================

def get_username(user) -> str:

    if user is None:
        return "user"

    return (
        getattr(user, "unique_id", None)
        or getattr(user, "uniqueId", None)
        or getattr(user, "nickname", None)
        or "user"
    )


def find_player_for_gift(
    gift_name: str,
    username: str,
) -> int:

    key = str(
        gift_name or ""
    ).lower().strip()

    if key in GIFT_MAP:
        return GIFT_MAP[key]

    for gift_key, player in GIFT_MAP.items():

        if gift_key in key or key in gift_key:
            return player

    return abs(hash(username)) % PLAYER_COUNT


# ============================================================
# API KEY VALIDATION
# ============================================================

async def validate_api_key(
    api_key: str,
) -> tuple[bool, str]:

    """
    API key üçün real network yoxlaması.

    VACIB:
    Network timeout artıq avtomatik olaraq
    "key qəbul olundu" hesab edilmir.

    SSL xətası ayrıca qaytarılır.
    """

    if not api_key or len(api_key.strip()) < 8:

        return (
            False,
            "API key çox qısadır / boşdur",
        )

    if not TIKTOK_AVAILABLE:

        return (
            False,
            "TikTokLive yüklənməyib",
        )

    api_key = api_key.strip()

    try:

        timeout = aiohttp.ClientTimeout(
            total=12
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key,
            "User-Agent": "TikTokLive/6.x",
        }

        connector = aiohttp.TCPConnector(
            ssl=get_ssl_context()
        )

        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
        ) as session:

            async with session.get(
                "https://api.eulerstream.com/webcast/room_info",
                params={
                    "unique_id": "tiktok"
                },
                headers=headers,
            ) as resp:

                text = (
                    await resp.text()
                )[:500].lower()

                print(
                    f"[API] Euler HTTP status: {resp.status}"
                )

                if resp.status in (
                    401,
                    403,
                ):

                    return (
                        False,
                        "API key yanlışdır / etibarsızdır",
                    )

                if (
                    "invalid" in text
                    and (
                        "api" in text
                        or "key" in text
                        or "token" in text
                    )
                ):

                    return (
                        False,
                        "API key yanlışdır / etibarsızdır",
                    )

                if (
                    "unauthorized" in text
                    or "forbidden" in text
                ):

                    return (
                        False,
                        "API key yanlışdır / etibarsızdır",
                    )

                # 2xx/3xx və explicit rejection yoxdursa
                # server cavabını müsbət hesab edirik.
                return (
                    True,
                    "API key qəbul olundu",
                )

    except asyncio.TimeoutError:

        print(
            "[API] Euler probe TIMEOUT"
        )

        return (
            False,
            "Euler API cavab vermədi — API key yoxlanıla bilmədi",
        )

    except ssl.SSLCertVerificationError as e:

        print(
            "[API] SSL CERTIFICATE ERROR:",
            repr(e),
        )

        return (
            False,
            "SSL sertifikat xətası — API key yoxlanıla bilmədi",
        )

    except aiohttp.ClientConnectorCertificateError as e:

        print(
            "[API] HTTPS CERTIFICATE ERROR:",
            repr(e),
        )

        return (
            False,
            "HTTPS sertifikat xətası — API key yoxlanıla bilmədi",
        )

    except aiohttp.ClientConnectorError as e:

        print(
            "[API] CONNECT ERROR:",
            repr(e),
        )

        return (
            False,
            f"Euler API bağlantı xətası: {e}",
        )

    except Exception as e:

        print(
            "[API] Euler probe error:",
            type(e).__name__,
            str(e),
        )

        return (
            False,
            f"API key yoxlanarkən xəta: {type(e).__name__}",
        )

    # ========================================================
    # WebDefaults
    # ========================================================

    try:

        WebDefaults.tiktok_sign_api_key = api_key

        return (
            True,
            "API key qəbul olundu",
        )

    except Exception as e:

        return (
            False,
            f"Key xətası: {e}",
        )


# ============================================================
# TIKTOK EVENTS
# ============================================================

async def on_connect(event):

    room_id = getattr(
        event,
        "room_id",
        None,
    )

    username = (
        getattr(
            event,
            "unique_id",
            None,
        )
        or current_user
    )

    print(
        f"[TikTok] CONNECTED @{username} room={room_id}"
    )

    await broadcast({
        "type": "status",
        "message": f"LIVE @{username}",
        "connected": True,
        "username": username,
        "room_id": room_id,
    })


async def on_disconnect(event):

    print(
        "[TikTok] DISCONNECTED"
    )

    await broadcast({
        "type": "status",
        "message": "TikTok disconnected",
        "connected": False,
    })


async def on_gift(event):

    try:

        gift = getattr(
            event,
            "gift",
            None,
        )

        if gift is None:
            return

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)

        gift_name = str(
            getattr(
                gift,
                "name",
                None,
            )
            or "Unknown Gift"
        ).strip()

        coins = (
            getattr(
                gift,
                "diamond_count",
                None,
            )
            or getattr(
                gift,
                "diamondCount",
                None,
            )
            or 1
        )

        try:
            coins = int(coins)
        except Exception:
            coins = 1

        count = (
            getattr(
                event,
                "repeat_count",
                None,
            )
            or getattr(
                event,
                "repeatCount",
                None,
            )
            or 1
        )

        try:
            count = int(count)
        except Exception:
            count = 1

        count = max(
            1,
            count,
        )

        gift_type = getattr(
            gift,
            "type",
            None,
        )

        streaking = bool(
            getattr(
                event,
                "streaking",
                False,
            )
        )

        repeat_end = getattr(
            event,
            "repeat_end",
            None,
        )

        try:
            repeat_end = int(
                repeat_end
            )
        except Exception:
            repeat_end = (
                1
                if repeat_end
                else 0
            )

        if (
            gift_type == 1
            and streaking
            and not repeat_end
        ):
            return

        supporters[username] = (
            supporters.get(
                username,
                0,
            )
            + coins * count
        )

        player_id = find_player_for_gift(
            gift_name,
            username,
        )

        points = (
            GIFT_POINTS * count
        )

        scores[player_id] += points

        await broadcast({
            "type": "gift",
            "username": username,
            "player_name": username,
            "gift_name": gift_name,
            "gift_key": gift_name.lower().strip(),
            "coins": coins,
            "count": count,
            "player_id": player_id,
            "points": points,
            "scores": scores[:],
            "avatar": "",
            "sound": True,
        })

        await broadcast_top()

    except Exception as exc:

        print(
            "[Gift] ERROR:",
            type(exc).__name__,
            str(exc),
        )


async def on_like(event):

    global total_likes
    global like_points_given

    try:

        amount = (
            getattr(
                event,
                "count",
                None,
            )
            or getattr(
                event,
                "total",
                None,
            )
            or 1
        )

        try:
            amount = int(amount)
        except Exception:
            amount = 1

        amount = max(
            1,
            amount,
        )

        total_likes += amount

        room_total = (
            getattr(
                event,
                "total",
                None,
            )
            or total_likes
        )

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)

        await broadcast({
            "type": "like",
            "amount": amount,
            "total": room_total,
            "username": username,
        })

        should_have = (
            total_likes // LIKE_EVERY
        )

        while like_points_given < should_have:

            like_points_given += 1

            player_id = (
                abs(hash(username))
                % PLAYER_COUNT
            )

            scores[player_id] += LIKE_POINTS

            await broadcast_scores()

    except Exception as exc:

        print(
            "[Like] ERROR:",
            type(exc).__name__,
            str(exc),
        )


async def on_follow(event):

    try:

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)

        player_id = (
            abs(hash(username))
            % PLAYER_COUNT
        )

        scores[player_id] += FOLLOW_POINTS

        await broadcast({
            "type": "follow",
            "username": username,
            "player_id": player_id,
            "points": FOLLOW_POINTS,
            "scores": scores[:],
        })

        await broadcast_scores()

    except Exception as exc:

        print(
            "[Follow] ERROR:",
            type(exc).__name__,
            str(exc),
        )


# ============================================================
# TIKTOK CONNECTION
# ============================================================

async def start_tiktok(
    username: str,
    api_key: str,
):

    global tiktok_client
    global current_user
    global current_api_key
    global _connect_task

    if not TIKTOK_AVAILABLE:

        await broadcast({
            "type": "status",
            "message": "TikTokLive yüklənməyib",
            "connected": False,
            "error": True,
        })

        return

    api_key = (
        api_key or ""
    ).strip()

    if not api_key:

        await broadcast({
            "type": "status",
            "message": "API key yoxdur",
            "connected": False,
            "error": True,
        })

        return

    # ========================================================
    # IMPORTANT:
    # connect zamanı da key-in WebDefaults-ə yazılması
    # ========================================================

    current_api_key = api_key

    try:

        WebDefaults.tiktok_sign_api_key = api_key

        print(
            "[API] WebDefaults API key configured"
        )

    except Exception as e:

        await broadcast({
            "type": "status",
            "message": f"API key tətbiq xətası: {e}",
            "connected": False,
            "error": True,
        })

        return

    # ========================================================
    # Previous connection
    # ========================================================

    if tiktok_client is not None:

        try:
            await tiktok_client.disconnect()
        except Exception:
            pass

        tiktok_client = None

    current_user = (
        username
        .lstrip("@")
        .strip()
    )

    if not current_user:

        await broadcast({
            "type": "status",
            "message": "Test rejimi (TikTok yoxdur)",
            "connected": False,
        })

        return

    # ========================================================
    # Client
    # ========================================================

    client = TikTokLiveClient(
        unique_id=current_user
    )

    tiktok_client = client

    connected_flag = asyncio.Event()

    async def _on_connect_wait(event):

        connected_flag.set()

        await on_connect(event)

    async def _on_disconnect_wait(event):

        await on_disconnect(event)

    client.add_listener(
        ConnectEvent,
        _on_connect_wait,
    )

    client.add_listener(
        DisconnectEvent,
        _on_disconnect_wait,
    )

    client.add_listener(
        GiftEvent,
        on_gift,
    )

    client.add_listener(
        LikeEvent,
        on_like,
    )

    client.add_listener(
        FollowEvent,
        on_follow,
    )

    print(
        f"[TikTok] Connecting to @{current_user} ..."
    )

    await broadcast({
        "type": "status",
        "message": f"@{current_user} yoxlanılır...",
        "connected": False,
    })

    try:

        # ====================================================
        # LIVE CHECK
        # ====================================================

        try:

            is_live = await asyncio.wait_for(
                client.is_live(),
                timeout=20,
            )

        except asyncio.TimeoutError:

            await broadcast({
                "type": "status",
                "message": "LIVE yoxlama vaxtı bitdi — şəbəkə / API key?",
                "connected": False,
                "error": True,
            })

            return

        except UserNotFoundError:

            await broadcast({
                "type": "status",
                "message": f"İstifadəçi tapılmadı: @{current_user}",
                "connected": False,
                "error": True,
            })

            return

        except ssl.SSLCertVerificationError as e:

            print(
                "[TikTok] SSL CERTIFICATE ERROR during is_live:",
                repr(e),
            )

            await broadcast({
                "type": "status",
                "message": "TikTok SSL sertifikat xətası — CA bundle yoxlanmalıdır",
                "connected": False,
                "error": True,
            })

            return

        except aiohttp.ClientConnectorCertificateError as e:

            print(
                "[TikTok] HTTPS CERTIFICATE ERROR during is_live:",
                repr(e),
            )

            await broadcast({
                "type": "status",
                "message": "TikTok HTTPS sertifikat xətası",
                "connected": False,
                "error": True,
            })

            return

        except Exception as e:

            err_name = type(e).__name__
            err_msg = str(e)

            print(
                "[TikTok] is_live error:",
                err_name,
                err_msg,
            )

            low = (
                err_msg or ""
            ).lower()

            if (
                "certificate verify failed"
                in low
                or "sslcertverificationerror"
                in low
            ):

                await broadcast({
                    "type": "status",
                    "message": "SSL sertifikat yoxlaması uğursuz oldu",
                    "connected": False,
                    "error": True,
                })

                return

            if (
                "not found" in low
                or "does not exist" in low
                or "usernotfound"
                in err_name.lower()
            ):

                await broadcast({
                    "type": "status",
                    "message": f"İstifadəçi tapılmadı: @{current_user}",
                    "connected": False,
                    "error": True,
                })

                return

            if (
                "offline" in low
                or "not live" in low
                or "useroffline"
                in err_name.lower()
            ):

                await broadcast({
                    "type": "status",
                    "message": f"@{current_user} hazırda LIVE deyil",
                    "connected": False,
                    "error": True,
                })

                return

            is_live = None

        # ====================================================
        # NOT LIVE
        # ====================================================

        if is_live is False:

            await broadcast({
                "type": "status",
                "message": f"@{current_user} hazırda LIVE deyil",
                "connected": False,
                "error": True,
            })

            return

        await broadcast({
            "type": "status",
            "message": f"@{current_user} qoşulur...",
            "connected": False,
        })

        # ====================================================
        # START
        # ====================================================

        try:

            task = await asyncio.wait_for(
                client.start(
                    fetch_live_check=True
                ),
                timeout=40,
            )

            _connect_task = task

        except asyncio.TimeoutError:

            await broadcast({
                "type": "status",
                "message": "Qoşulma vaxtı bitdi (start) — LIVE / API key / şəbəkə yoxla",
                "connected": False,
                "error": True,
            })

            return

        except UserOfflineError:

            await broadcast({
                "type": "status",
                "message": f"@{current_user} hazırda LIVE deyil",
                "connected": False,
                "error": True,
            })

            return

        except UserNotFoundError:

            await broadcast({
                "type": "status",
                "message": f"İstifadəçi tapılmadı: @{current_user}",
                "connected": False,
                "error": True,
            })

            return

        except AlreadyConnectedError:

            await broadcast({
                "type": "status",
                "message": f"LIVE @{current_user}",
                "connected": True,
                "username": current_user,
            })

            return

        except ssl.SSLCertVerificationError as e:

            print(
                "[TikTok] SSL CERTIFICATE ERROR during start:",
                repr(e),
            )

            await broadcast({
                "type": "status",
                "message": "Webcast SSL sertifikat xətası — CA bundle problemi",
                "connected": False,
                "error": True,
            })

            return

        except aiohttp.ClientConnectorCertificateError as e:

            print(
                "[TikTok] HTTPS CERTIFICATE ERROR during start:",
                repr(e),
            )

            await broadcast({
                "type": "status",
                "message": "Webcast HTTPS sertifikat xətası",
                "connected": False,
                "error": True,
            })

            return

        except Exception as e:

            err_name = type(e).__name__
            err_msg = str(e)

            print(
                "[TikTok] start error:",
                err_name,
                err_msg,
            )

            low = (
                err_msg or ""
            ).lower()

            if (
                "certificate verify failed"
                in low
                or "sslcertverificationerror"
                in low
            ):

                msg = (
                    "Webcast SSL sertifikat xətası"
                )

            elif (
                "offline" in low
                or "not live" in low
            ):

                msg = (
                    f"@{current_user} hazırda LIVE deyil"
                )

            elif (
                "not found" in low
                or "does not exist" in low
            ):

                msg = (
                    f"İstifadəçi tapılmadı: @{current_user}"
                )

            elif (
                "api" in low
                and (
                    "key" in low
                    or "sign" in low
                    or "401" in low
                    or "403" in low
                )
            ):

                msg = (
                    "API key etibarsızdır və ya limit bitib"
                )

            elif (
                "sign" in low
                or "euler" in low
                or "403" in low
                or "401" in low
            ):

                msg = (
                    f"İmza/API xətası: {err_msg}"
                )[:160]

            else:

                msg = (
                    f"Bağlantı xətası: "
                    f"{err_name}: {err_msg}"
                )[:180]

            await broadcast({
                "type": "status",
                "message": msg,
                "connected": False,
                "error": True,
            })

            return

        # ====================================================
        # CONNECT EVENT WAIT
        # ====================================================

        if not connected_flag.is_set():

            try:

                await asyncio.wait_for(
                    connected_flag.wait(),
                    timeout=25,
                )

            except asyncio.TimeoutError:

                detail = ""

                try:

                    if (
                        _connect_task
                        and _connect_task.done()
                    ):

                        exc = (
                            _connect_task.exception()
                        )

                        if exc:

                            detail = (
                                f" ({type(exc).__name__}: {exc})"
                            )[:120]

                except Exception:
                    pass

                print(
                    f"[TikTok] ConnectEvent timeout "
                    f"@{current_user}{detail}"
                )

                try:
                    await client.disconnect()
                except Exception:
                    pass

                await broadcast({
                    "type": "status",
                    "message": (
                        f"@{current_user} LIVE görünür "
                        f"amma Webcast-ə qoşulmadı"
                        f"{detail}"
                    )[:200],
                    "connected": False,
                    "error": True,
                })

                return

        print(
            f"[TikTok] Connect confirmed @{current_user}"
        )

    except ssl.SSLCertVerificationError as e:

        print(
            "[TikTok] SSL ERROR:",
            repr(e),
        )

        await broadcast({
            "type": "status",
            "message": "TikTok SSL sertifikat xətası",
            "connected": False,
            "error": True,
        })

    except Exception as e:

        print(
            "[TikTok] Connect error:",
            type(e).__name__,
            str(e),
        )

        await broadcast({
            "type": "status",
            "message": (
                f"Bağlantı xətası: {e}"
            )[:200],
            "connected": False,
            "error": True,
        })


# ============================================================
# WEBSOCKET HANDLER
# ============================================================

async def websocket_handler(request):

    global current_api_key
    global scores
    global supporters
    global total_likes
    global like_points_given

    ws = web.WebSocketResponse()

    await ws.prepare(request)

    clients.add(ws)

    print(
        "[WS] Client connected"
    )

    try:

        async for msg in ws:

            if msg.type != aiohttp.WSMsgType.TEXT:
                continue

            try:

                data = json.loads(
                    msg.data
                )

            except Exception:
                continue

            msg_type = data.get(
                "type"
            )

            # =================================================
            # API KEY
            # =================================================

            if msg_type == "set_api_key":

                api_key = (
                    data.get(
                        "api_key"
                    )
                    or ""
                ).strip()

                ok, message = (
                    await validate_api_key(
                        api_key
                    )
                )

                if ok:

                    current_api_key = api_key

                else:

                    if (
                        current_api_key
                        == api_key
                    ):
                        current_api_key = ""

                await ws.send_str(
                    json.dumps(
                        {
                            "type":
                                "api_key_result",
                            "ok": ok,
                            "message":
                                message,
                        },
                        ensure_ascii=False,
                    )
                )

            # =================================================
            # CONNECT
            # =================================================

            elif msg_type in (
                "set_user",
                "connect",
            ):

                username = (
                    data.get(
                        "username"
                    )
                    or ""
                ).strip()

                api_key = (
                    data.get(
                        "api_key"
                    )
                    or current_api_key
                    or ""
                ).strip()

                if username and not api_key:

                    await ws.send_str(
                        json.dumps(
                            {
                                "type":
                                    "status",
                                "message":
                                    "Əvvəlcə API key yazın",
                                "connected":
                                    False,
                                "error":
                                    True,
                            },
                            ensure_ascii=False,
                        )
                    )

                    continue

                asyncio.create_task(
                    start_tiktok(
                        username,
                        api_key,
                    )
                )

            # =================================================
            # RESET
            # =================================================

            elif msg_type == "reset":

                scores = [
                    0
                    for _ in range(
                        PLAYER_COUNT
                    )
                ]

                supporters = {}

                total_likes = 0

                like_points_given = 0

                await broadcast_scores()

                await broadcast_top()

    finally:

        clients.discard(ws)

        print(
            "[WS] Client disconnected"
        )

    return ws


# ============================================================
# INDEX
# ============================================================

async def index_handler(request):

    return web.FileResponse(
        ROOT / "index.html"
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    app = web.Application()

    app.router.add_get(
        "/",
        index_handler,
    )

    app.router.add_get(
        "/ws",
        websocket_handler,
    )

    app.router.add_static(
        "/",
        ROOT,
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        HOST,
        PORT,
    )

    await site.start()

    print(
        f"Server started → "
        f"http://{HOST}:{PORT}"
    )

    while True:

        await asyncio.sleep(
            3600
        )


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "Stopped."
        )
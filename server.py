#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType

import aiohttp
from aiohttp import web

# ============================================================
# GÜCLÜ MOCK – EulerApiSdk-nin bütün alt modullarını tutur
# ============================================================

def fetch_webcast_url(*args, **kwargs):
    print("⚠️ fetch_webcast_url MOCK çağırıldı!")
    print("args:", args)
    print("kwargs:", kwargs)
    # İstədiyiniz cavabı qaytarın
    return {"url": "https://eulerstream.com"}


class FakeModule(ModuleType):
    """Hər cür alt modul sorğusuna cavab verən saxta modul"""
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []          # paket kimi görünsün
        self.__package__ = name

    def __getattr__(self, name):
        # Əsas funksiyanı tuturuq
        if name in ("fetch_webcast_url", "sign_webcast_url"):
            return fetch_webcast_url

        # Hər hansı digər atribut/modul sorğusu üçün yeni FakeModule qaytarırıq
        full_name = f"{self.__name__}.{name}"
        if full_name not in sys.modules:
            fake = FakeModule(full_name)
            sys.modules[full_name] = fake
        return sys.modules[full_name]


# Əsas paketləri qeydiyyatdan keçiririk
euler = FakeModule("EulerApiSdk")
sys.modules["EulerApiSdk"] = euler
sys.modules["EulerApiSdk.api"] = FakeModule("EulerApiSdk.api")
sys.modules["EulerApiSdk.api.tik_tok_live"] = FakeModule("EulerApiSdk.api.tik_tok_live")
sys.modules["EulerApiSdk.models"] = FakeModule("EulerApiSdk.models")
sys.modules["EulerApiSdk.types"] = FakeModule("EulerApiSdk.types")

print("=" * 70)
print("[MOCK] EulerApiSdk (güclü versiya) aktivdir → fetch_webcast_url yönləndirilir")
print("=" * 70)


# ============================================================
# TikTokLive
# ============================================================

TIKTOK_AVAILABLE = False

TikTokLiveClient = None
ConnectEvent = None
DisconnectEvent = None
GiftEvent = None
LikeEvent = None
FollowEvent = None
ShareEvent = None
CommentEvent = None


try:
    from TikTokLive import TikTokLiveClient

    from TikTokLive.events import (
        ConnectEvent,
        DisconnectEvent,
        GiftEvent,
        LikeEvent,
        FollowEvent,
        ShareEvent,
        CommentEvent,
    )

    TIKTOK_AVAILABLE = True

    print("=" * 70)
    print("[TikTokLive] IMPORT OK")
    print("[TikTokLive] Client:", TikTokLiveClient)
    print("=" * 70)

except Exception as exc:
    print("=" * 70)
    print("[TikTokLive] IMPORT FAILED")
    print(type(exc).__name__, str(exc))
    print("=" * 70)


# ============================================================
# SERVER
# ============================================================

HOST = "0.0.0.0"
PORT = 8000

PLAYER_COUNT = 7

ROOT = Path(__file__).resolve().parent


# ============================================================
# GAME SETTINGS
# ============================================================

GIFT_POINTS = 1

FOLLOW_POINTS = 2

LIKE_POINTS = 1
LIKE_EVERY = 20

AZERBAIJAN_PLAYER = 0
TURKEY_PLAYER = 1


# ============================================================
# GIFT MAP
# ============================================================

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
tiktok_task = None

current_user = ""
current_room_id = None


# ============================================================
# BROADCAST
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
    await broadcast(
        {
            "type": "scores",
            "scores": scores[:],
        }
    )


async def broadcast_top() -> None:
    top = sorted(
        supporters.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:3]

    await broadcast(
        {
            "type": "top_supporters",
            "list": [
                {
                    "username": username,
                    "coins": coins,
                }
                for username, coins in top
            ],
        }
    )


# ============================================================
# USER HELPERS
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


def get_avatar(user) -> str:
    if user is None:
        return ""

    candidates = []

    def walk(obj, depth=0):
        if obj is None or depth > 5:
            return

        if isinstance(obj, str):
            if obj.startswith("http"):
                candidates.append(obj)
            return

        if isinstance(obj, dict):
            for value in obj.values():
                walk(value, depth + 1)
            return

        if isinstance(obj, (list, tuple)):
            for value in obj[:10]:
                walk(value, depth + 1)
            return

        for attr in (
            "url_list",
            "urlList",
            "urls",
            "url",
            "uri",
            "avatar_thumb",
            "avatar_medium",
            "avatar",
            "profile_picture",
        ):
            try:
                walk(
                    getattr(obj, attr, None),
                    depth + 1,
                )
            except Exception:
                pass

        data = getattr(obj, "__dict__", None)

        if isinstance(data, dict):
            for value in data.values():
                walk(value, depth + 1)

    walk(user)

    return candidates[0] if candidates else ""


# ============================================================
# GIFT -> PLAYER
# ============================================================

def find_player_for_gift(
    gift_name: str,
    username: str,
) -> int:

    key = str(gift_name or "").lower().strip()

    player_id = GIFT_MAP.get(key)

    if player_id is not None:
        return player_id

    for gift_key, player in GIFT_MAP.items():
        if gift_key in key or key in gift_key:
            return player

    return abs(hash(username)) % PLAYER_COUNT


# ============================================================
# CONNECT
# ============================================================

async def on_connect(event) -> None:

    room_id = getattr(event, "room_id", None)

    if room_id is None and tiktok_client is not None:
        room_id = getattr(
            tiktok_client,
            "room_id",
            None,
        )

    username = getattr(
        event,
        "unique_id",
        None,
    ) or current_user

    print(
        f"[TikTok] CONNECTED @{username} "
        f"room={room_id}"
    )

    await broadcast(
        {
            "type": "status",
            "message": f"LIVE @{username}",
            "connected": True,
            "username": username,
            "room_id": room_id,
        }
    )


# ============================================================
# DISCONNECT
# ============================================================

async def on_disconnect(event) -> None:

    print("[TikTok] DISCONNECTED")

    await broadcast(
        {
            "type": "status",
            "message": "TikTok disconnected",
            "connected": False,
        }
    )


# ============================================================
# GIFT
# ============================================================

async def on_gift(event) -> None:

    try:

        gift = getattr(event, "gift", None)

        if gift is None:
            return

        user = getattr(event, "user", None)

        username = get_username(user)
        avatar = get_avatar(user)

        gift_name = (
            getattr(gift, "name", None)
            or "Unknown Gift"
        )

        gift_name = str(gift_name).strip()

        coins = (
            getattr(gift, "diamond_count", None)
            or getattr(gift, "diamondCount", None)
            or 1
        )

        try:
            coins = int(coins)
        except Exception:
            coins = 1

        count = (
            getattr(event, "repeat_count", None)
            or getattr(event, "repeatCount", None)
            or 1
        )

        try:
            count = int(count)
        except Exception:
            count = 1

        count = max(1, count)

        # ====================================================
        # STREAK
        # ====================================================

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
            repeat_end = int(repeat_end)
        except Exception:
            repeat_end = 1 if repeat_end else 0

        # TikTokLive 6.6.5:
        # type == 1 => streakable gift
        if (
            gift_type == 1
            and streaking
            and not repeat_end
        ):
            return

        # ====================================================
        # LOG
        # ====================================================

        print(
            f"[Gift] @{username} -> "
            f"{gift_name} x{count} "
            f"({coins} diamonds)"
        )

        # ====================================================
        # SUPPORTER
        # ====================================================

        supporters[username] = (
            supporters.get(username, 0)
            + coins * count
        )

        # ====================================================
        # PLAYER
        # ====================================================

        player_id = find_player_for_gift(
            gift_name,
            username,
        )

        points = GIFT_POINTS * count

        scores[player_id] += points

        # ====================================================
        # FRONTEND
        # ====================================================

        await broadcast(
            {
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

                "avatar": avatar,

                "sound": True,
            }
        )

        await broadcast_top()

    except Exception as exc:

        print(
            "[Gift] ERROR:",
            type(exc).__name__,
            str(exc),
        )


# ============================================================
# LIKE
# ============================================================

async def on_like(event) -> None:

    global total_likes
    global like_points_given

    try:

        amount = getattr(
            event,
            "count",
            None,
        )

        if amount is None:
            amount = getattr(
                event,
                "total",
                None,
            )

        try:
            amount = int(amount)
        except Exception:
            amount = 1

        amount = max(1, amount)

        total_likes += amount

        room_total = getattr(
            event,
            "total",
            None,
        )

        try:
            room_total = int(room_total)
        except Exception:
            room_total = total_likes

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)
        avatar = get_avatar(user)

        await broadcast(
            {
                "type": "like",
                "amount": amount,
                "total": room_total,
                "username": username,
            }
        )

        # Every 20 likes = 1 point

        should_have = total_likes // LIKE_EVERY

        new_points = (
            should_have
            - like_points_given
        )

        if new_points <= 0:
            return

        like_points_given = should_have

        points = new_points * LIKE_POINTS

        scores[AZERBAIJAN_PLAYER] += points

        await broadcast(
            {
                "type": "gift",

                "username": username,

                "player_name": username,

                "gift_name": "Like",

                "gift_key": "like",

                "coins": 0,

                "count": new_points,

                "player_id": AZERBAIJAN_PLAYER,

                "points": points,

                "scores": scores[:],

                "avatar": avatar,

                "sound": True,

                "reason": "like",
            }
        )

        await broadcast_top()

    except Exception as exc:

        print(
            "[Like] ERROR:",
            type(exc).__name__,
            str(exc),
        )


# ============================================================
# FOLLOW
# ============================================================

async def on_follow(event) -> None:

    try:

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)
        avatar = get_avatar(user)

        player_id = TURKEY_PLAYER

        scores[player_id] += FOLLOW_POINTS

        await broadcast(
            {
                "type": "follow",
                "username": username,
            }
        )

        await broadcast(
            {
                "type": "gift",

                "username": username,

                "player_name": username,

                "gift_name": "Follow",

                "gift_key": "follow",

                "coins": 0,

                "count": 1,

                "player_id": player_id,

                "points": FOLLOW_POINTS,

                "scores": scores[:],

                "avatar": avatar,

                "sound": True,

                "reason": "follow",
            }
        )

        await broadcast_top()

    except Exception as exc:

        print(
            "[Follow] ERROR:",
            type(exc).__name__,
            str(exc),
        )


# ============================================================
# SHARE
# ============================================================

async def on_share(event) -> None:

    try:

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)

        await broadcast(
            {
                "type": "share",
                "username": username,
            }
        )

    except Exception as exc:

        print(
            "[Share] ERROR:",
            type(exc).__name__,
            str(exc),
        )


# ============================================================
# COMMENT
# ============================================================

async def on_comment(event) -> None:

    try:

        user = getattr(
            event,
            "user",
            None,
        )

        username = get_username(user)

        comment = (
            getattr(
                event,
                "comment",
                None,
            )
            or getattr(
                event,
                "content",
                None,
            )
            or ""
        )

        await broadcast(
            {
                "type": "comment",
                "username": username,
                "comment": comment,
            }
        )

    except Exception as exc:

        print(
            "[Comment] ERROR:",
            type(exc).__name__,
            str(exc),
        )


# ============================================================
# STOP TIKTOK
# ============================================================

async def stop_tiktok() -> None:

    global tiktok_client
    global tiktok_task
    global current_room_id

    client = tiktok_client
    task = tiktok_task

    tiktok_client = None
    tiktok_task = None
    current_room_id = None

    if client is not None:

        try:

            result = client.disconnect()

            if asyncio.iscoroutine(result):
                await result

        except Exception as exc:

            print(
                "[TikTok] disconnect error:",
                type(exc).__name__,
                str(exc),
            )

    if task is not None:

        try:

            if not task.done():
                task.cancel()

        except Exception:
            pass


# ============================================================
# START TIKTOK
# ============================================================

async def start_tiktok(username: str) -> None:

    global tiktok_client
    global tiktok_task
    global current_user
    global current_room_id

    if not TIKTOK_AVAILABLE:

        await broadcast(
            {
                "type": "status",
                "message": "TikTokLive import edilmedi.",
                "connected": False,
            }
        )

        return

    username = (
        username
        or ""
    ).strip().lstrip("@")

    if not username:

        await broadcast(
            {
                "type": "status",
                "message": "Username boşdur.",
                "connected": False,
            }
        )

        return

    await stop_tiktok()

    current_user = username

    await broadcast(
        {
            "type": "status",
            "message": f"Yoxlanılır @{username} ...",
            "connected": False,
            "username": username,
        }
    )

    print(
        f"[TikTok] Checking @{username}"
    )

    # ========================================================
    # CLIENT
    # ========================================================

    try:

        client = TikTokLiveClient(
            unique_id=username
        )

    except Exception as exc:

        print(
            "[TikTok] client creation ERROR:",
            type(exc).__name__,
            str(exc),
        )

        await broadcast(
            {
                "type": "status",
                "message":
                    f"Client xətası: {str(exc)[:250]}",
                "connected": False,
            }
        )

        return

    # ========================================================
    # LIVE CHECK
    # ========================================================

    try:

        is_live = await client.is_live()

    except Exception as exc:

        error = str(exc)

        print(
            "[TikTok] is_live ERROR:",
            type(exc).__name__,
            error,
        )

        await broadcast(
            {
                "type": "status",
                "message":
                    f"LIVE yoxlama xətası: {error[:250]}",
                "connected": False,
                "error": error,
            }
        )

        return

    if not is_live:

        await broadcast(
            {
                "type": "status",
                "message":
                    f"@{username} hazırda LIVE deyil",
                "connected": False,
                "username": username,
            }
        )

        return

    # ========================================================
    # EVENT LISTENERS
    # ========================================================

    try:

        client.add_listener(
            ConnectEvent,
            on_connect,
        )

        client.add_listener(
            DisconnectEvent,
            on_disconnect,
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

        client.add_listener(
            ShareEvent,
            on_share,
        )

        client.add_listener(
            CommentEvent,
            on_comment,
        )

    except Exception as exc:

        print(
            "[TikTok] event registration ERROR:",
            type(exc).__name__,
            str(exc),
        )

        await broadcast(
            {
                "type": "status",
                "message":
                    f"Event xətası: {str(exc)[:250]}",
                "connected": False,
            }
        )

        return

    # ========================================================
    # SAVE CLIENT
    # ========================================================

    tiktok_client = client

    await broadcast(
        {
            "type": "status",
            "message":
                f"LIVE tapıldı, qoşulur @{username} ...",
            "connected": False,
            "username": username,
        }
    )

    # ========================================================
    # START
    # ========================================================

    try:

        task = await client.start(
            fetch_live_check=False,
            fetch_gift_info=True,
        )

        tiktok_task = task

        current_room_id = getattr(
            client,
            "room_id",
            None,
        )

        print(
            f"[TikTok] START OK @{username}"
        )

    except Exception as exc:

        error = str(exc)

        print(
            "[TikTok] START ERROR:",
            type(exc).__name__,
            error,
        )

        tiktok_client = None
        tiktok_task = None
        current_room_id = None

        await broadcast(
            {
                "type": "status",
                "message":
                    f"Qoşulma xətası: {error[:300]}",
                "connected": False,
                "error": error,
            }
        )


# ============================================================
# WEBSOCKET
# ============================================================

async def ws_handler(request):

    global total_likes
    global like_points_given

    ws = web.WebSocketResponse(
        heartbeat=30
    )

    await ws.prepare(request)

    clients.add(ws)

    print(
        "[WS] client +1 =",
        len(clients),
    )

    await ws.send_str(
        json.dumps(
            {
                "type": "init",

                "scores": scores[:],

                "total_likes": total_likes,

                "supporters": [
                    {
                        "username": username,
                        "coins": coins,
                    }
                    for username, coins
                    in sorted(
                        supporters.items(),
                        key=lambda item: -item[1],
                    )[:3]
                ],

                "gift_map": GIFT_MAP,

                "connected":
                    (
                        tiktok_client is not None
                    ),

                "username": current_user,

                "room_id": current_room_id,
            },
            ensure_ascii=False,
        )
    )

    try:

        async for msg in ws:

            if msg.type != aiohttp.WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except Exception:
                continue

            message_type = data.get("type")

            # =================================================
            # SET USER
            # =================================================

            if message_type == "set_user":

                username = (
                    data.get("username")
                    or ""
                ).strip().lstrip("@")

                if username:

                    asyncio.create_task(
                        start_tiktok(username)
                    )

                else:

                    await stop_tiktok()

                    await broadcast(
                        {
                            "type": "status",
                            "message": "Test rejimi",
                            "connected": False,
                        }
                    )

            # =================================================
            # TEST GIFT
            # =================================================

            elif message_type == "gift":

                try:
                    player_id = (
                        int(
                            data.get(
                                "player_id",
                                0,
                            )
                        )
                        % PLAYER_COUNT
                    )
                except Exception:
                    player_id = 0

                try:
                    points = int(
                        data.get(
                            "points",
                            GIFT_POINTS,
                        )
                    )
                except Exception:
                    points = GIFT_POINTS

                username = (
                    data.get(
                        "username",
                        "test",
                    )
                    or "test"
                )

                gift_name = (
                    data.get(
                        "gift_name",
                        "Test",
                    )
                    or "Test"
                )

                try:
                    coins = int(
                        data.get(
                            "coins",
                            1,
                        )
                    )
                except Exception:
                    coins = 1

                supporters[username] = (
                    supporters.get(
                        username,
                        0,
                    )
                    + coins
                )

                scores[player_id] += points

                await broadcast(
                    {
                        "type": "gift",

                        "username": username,

                        "player_name": username,

                        "gift_name": gift_name,

                        "gift_key":
                            gift_name.lower().strip(),

                        "player_id": player_id,

                        "points": points,

                        "coins": coins,

                        "count": 1,

                        "scores": scores[:],

                        "avatar": "",

                        "sound": True,
                    }
                )

                await broadcast_top()

            # =================================================
            # RESET
            # =================================================

            elif message_type == "reset_scores":

                for i in range(PLAYER_COUNT):
                    scores[i] = 0

                total_likes = 0
                like_points_given = 0

                supporters.clear()

                await broadcast_scores()
                await broadcast_top()

    except Exception as exc:

        print(
            "[WS] ERROR:",
            type(exc).__name__,
            str(exc),
        )

    finally:

        clients.discard(ws)

        print(
            "[WS] client -1 =",
            len(clients),
        )

    return ws


# ============================================================
# HTTP INDEX
# ============================================================

async def index(request):

    candidates = (
        "football_gift_race_fixed.html",
        "index.html",
    )

    for filename in candidates:

        path = ROOT / filename

        if path.is_file():

            response = web.FileResponse(path)

            response.headers["Cache-Control"] = (
                "no-store, no-cache, "
                "must-revalidate, max-age=0"
            )

            response.headers["Pragma"] = "no-cache"

            return response

    return web.Response(
        text="index.html not found",
        status=404,
    )


# ============================================================
# HEALTH
# ============================================================

async def health(request):

    return web.json_response(
        {
            "ok": True,
            "tiktoklive": TIKTOK_AVAILABLE,
            "username": current_user,
            "connected":
                tiktok_client is not None,
        }
    )


# ============================================================
# APP
# ============================================================

def create_app():

    app = web.Application()

    app.router.add_get(
        "/",
        index,
    )

    app.router.add_get(
        "/index.html",
        index,
    )

    app.router.add_get(
        "/football_gift_race_fixed.html",
        index,
    )

    app.router.add_get(
        "/ws",
        ws_handler,
    )

    app.router.add_get(
        "/health",
        health,
    )

    assets = ROOT / "assets"

    if assets.is_dir():

        app.router.add_static(
            "/assets/",
            assets,
        )

    return app


# ============================================================
# SERVER MAIN
# ============================================================

async def main():

    app = create_app()

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        HOST,
        PORT,
    )

    await site.start()

    print("=" * 70)
    print("Football Gift Race + TikTok Live")
    print(f"http://127.0.0.1:{PORT}")
    print("=" * 70)

    print(
        "[Status] TikTokLive:",
        "OK" if TIKTOK_AVAILABLE else "UNAVAILABLE",
    )

    print(
        "[Status] EulerApiSdk MOCK aktivdir → fetch_webcast_url yönləndirilir"
    )

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
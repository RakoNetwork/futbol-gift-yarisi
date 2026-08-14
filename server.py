#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp import web
import aiohttp


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
    print("=" * 70)
    print("[TikTokLive] Client:", TikTokLiveClient)
    print("=" * 70)

except Exception as e:

    print("=" * 70)
    print("[TikTokLive] IMPORT FAILED")
    print(type(e).__name__)
    print(str(e))
    print("=" * 70)

    TIKTOK_AVAILABLE = False


# ============================================================
# SERVER
# ============================================================

HOST = "0.0.0.0"
PORT = 8000

PLAYER_COUNT = 7

ROOT = Path(__file__).parent.resolve()


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


GIFT_POINTS = 1
FOLLOW_POINTS = 2
LIKE_POINTS = 1
LIKE_EVERY = 20

AZERBAIJAN_PLAYER = 0
TURKEY_PLAYER = 1


# ============================================================
# STATE
# ============================================================

clients = set()

scores = [0] * PLAYER_COUNT

supporters = {}

total_likes = 0
like_points_given = 0

tiktok_client = None
tiktok_task = None

current_user = ""
current_room_id = None


# ============================================================
# BROADCAST
# ============================================================

async def broadcast(data: dict):

    if not clients:
        return

    message = json.dumps(
        data,
        ensure_ascii=False
    )

    dead = []

    for ws in list(clients):

        try:
            await ws.send_str(message)

        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)


async def broadcast_scores():

    await broadcast({
        "type": "scores",
        "scores": scores[:]
    })


async def broadcast_top():

    top = sorted(
        supporters.items(),
        key=lambda item: item[1],
        reverse=True
    )[:3]

    await broadcast({
        "type": "top_supporters",

        "list": [
            {
                "username": username,
                "coins": coins
            }

            for username, coins in top
        ]
    })


# ============================================================
# USER HELPERS
# ============================================================

def get_username(user):

    if user is None:
        return "user"

    return (
        getattr(user, "nickname", None)
        or getattr(user, "unique_id", None)
        or getattr(user, "uniqueId", None)
        or "user"
    )


def get_avatar(user):

    if user is None:
        return ""

    candidates = []

    def walk(obj, depth=0):

        if obj is None:
            return

        if depth > 5:
            return

        if isinstance(obj, str):

            if obj.startswith("http"):

                if any(
                    x in obj.lower()
                    for x in (
                        "tiktok",
                        "byteoversea",
                        "avatar",
                        "avt",
                        ".webp",
                        ".jpg",
                        ".jpeg",
                        ".png",
                    )
                ):
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
                    depth + 1
                )

            except Exception:
                pass

        data = getattr(
            obj,
            "__dict__",
            None
        )

        if isinstance(data, dict):

            for value in data.values():
                walk(value, depth + 1)

    walk(user)

    if candidates:
        return candidates[0]

    return ""


# ============================================================
# GIFT PLAYER
# ============================================================

def find_player_for_gift(gift_name: str, username: str):

    key = (
        gift_name
        or ""
    ).lower().strip()

    player_id = GIFT_MAP.get(key)

    if player_id is not None:
        return player_id

    for gift_key, player in GIFT_MAP.items():

        if (
            gift_key in key
            or key in gift_key
        ):
            return player

    return (
        abs(hash(username))
        % PLAYER_COUNT
    )


# ============================================================
# TIKTOK EVENTS
# ============================================================

async def on_connect(event):

    room_id = None

    if tiktok_client is not None:

        room_id = getattr(
            tiktok_client,
            "room_id",
            None
        )

        if room_id is None:

            room_id = getattr(
                tiktok_client,
                "roomId",
                None
            )

    username = getattr(
        event,
        "unique_id",
        None
    )

    if not username:
        username = current_user

    print(
        f"[TikTok] CONNECTED @{username} "
        f"room={room_id}"
    )

    await broadcast({

        "type": "status",

        "message":
            f"LIVE @{username}",

        "connected": True,

        "username":
            username,

        "room_id":
            room_id
    })


async def on_disconnect(event):

    print("[TikTok] DISCONNECTED")

    await broadcast({

        "type": "status",

        "message":
            "TikTok disconnected",

        "connected": False

    })


async def on_gift(event):

    try:

        gift = getattr(
            event,
            "gift",
            None
        )

        if gift is None:
            return

        user = getattr(
            event,
            "user",
            None
        )

        username = get_username(user)
        avatar = get_avatar(user)

        gift_name = (
            getattr(
                gift,
                "name",
                None
            )

            or "Unknown Gift"
        )

        gift_name = str(
            gift_name
        ).strip()

        coins = (
            getattr(
                gift,
                "diamond_count",
                None
            )

            or getattr(
                gift,
                "diamondCount",
                None
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
                None
            )

            or getattr(
                event,
                "repeatCount",
                None
            )

            or 1
        )

        try:
            count = int(count)
        except Exception:
            count = 1

        if count < 1:
            count = 1

        # ----------------------------------------------------
        # STREAK
        # ----------------------------------------------------

        gift_type = getattr(
            gift,
            "type",
            None
        )

        streakable = bool(
            getattr(
                gift,
                "streakable",
                False
            )
            or gift_type == 1
        )

        streaking = bool(
            getattr(
                event,
                "streaking",
                False
            )
        )

        repeat_end = getattr(
            event,
            "repeat_end",
            None
        )

        if repeat_end is None:

            repeat_end = getattr(
                event,
                "repeatEnd",
                None
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
            streakable
            and streaking
            and not repeat_end
        ):
            return

        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

        print(
            f"[Gift] @{username} "
            f"-> {gift_name} "
            f"x{count} "
            f"({coins} diamonds)"
        )

        # ----------------------------------------------------
        # SUPPORTER
        # ----------------------------------------------------

        supporters[username] = (
            supporters.get(
                username,
                0
            )
            + (
                coins
                * count
            )
        )

        # ----------------------------------------------------
        # PLAYER
        # ----------------------------------------------------

        player_id = find_player_for_gift(
            gift_name,
            username
        )

        points = (
            GIFT_POINTS
            * max(1, count)
        )

        scores[player_id] += points

        # ----------------------------------------------------
        # FRONTEND
        # ----------------------------------------------------

        await broadcast({

            "type": "gift",

            "username":
                username,

            "player_name":
                username,

            "gift_name":
                gift_name,

            "gift_key":
                gift_name.lower().strip(),

            "coins":
                coins,

            "count":
                count,

            "player_id":
                player_id,

            "points":
                points,

            "scores":
                scores[:],

            "avatar":
                avatar,

            "sound":
                True

        })

        await broadcast_top()

    except Exception as e:

        print(
            "[Gift] ERROR:",
            type(e).__name__,
            str(e)
        )


async def on_like(event):

    global total_likes
    global like_points_given

    try:

        amount = getattr(
            event,
            "count",
            None
        )

        if amount is None:

            amount = getattr(
                event,
                "total",
                None
            )

        try:
            amount = int(amount)
        except Exception:
            amount = 1

        if amount < 1:
            amount = 1

        total_likes += amount

        room_total = getattr(
            event,
            "total",
            None
        )

        try:

            room_total = int(
                room_total
            )

        except Exception:

            room_total = total_likes

        user = getattr(
            event,
            "user",
            None
        )

        username = get_username(user)
        avatar = get_avatar(user)

        await broadcast({

            "type": "like",

            "amount":
                amount,

            "total":
                room_total,

            "username":
                username

        })

        # ----------------------------------------------------
        # Every 20 likes = 1 point
        # ----------------------------------------------------

        should_have = (
            total_likes
            // LIKE_EVERY
        )

        new_points = (
            should_have
            - like_points_given
        )

        if new_points <= 0:
            return

        like_points_given = (
            should_have
        )

        points = (
            new_points
            * LIKE_POINTS
        )

        scores[
            AZERBAIJAN_PLAYER
        ] += points

        await broadcast({

            "type": "gift",

            "username":
                username,

            "player_name":
                username,

            "gift_name":
                "Like",

            "gift_key":
                "like",

            "coins":
                0,

            "count":
                new_points,

            "player_id":
                AZERBAIJAN_PLAYER,

            "points":
                points,

            "scores":
                scores[:],

            "avatar":
                avatar,

            "sound":
                True,

            "reason":
                "like"

        })

        await broadcast_top()

    except Exception as e:

        print(
            "[Like] ERROR:",
            type(e).__name__,
            str(e)
        )


async def on_follow(event):

    try:

        user = getattr(
            event,
            "user",
            None
        )

        username = get_username(user)
        avatar = get_avatar(user)

        player_id = TURKEY_PLAYER

        scores[player_id] += (
            FOLLOW_POINTS
        )

        await broadcast({

            "type":
                "follow",

            "username":
                username

        })

        await broadcast({

            "type":
                "gift",

            "username":
                username,

            "player_name":
                username,

            "gift_name":
                "Follow",

            "gift_key":
                "follow",

            "coins":
                0,

            "count":
                1,

            "player_id":
                player_id,

            "points":
                FOLLOW_POINTS,

            "scores":
                scores[:],

            "avatar":
                avatar,

            "sound":
                True,

            "reason":
                "follow"

        })

        await broadcast_top()

    except Exception as e:

        print(
            "[Follow] ERROR:",
            type(e).__name__,
            str(e)
        )


async def on_share(event):

    try:

        user = getattr(
            event,
            "user",
            None
        )

        username = get_username(user)

        await broadcast({

            "type":
                "share",

            "username":
                username

        })

    except Exception as e:

        print(
            "[Share] ERROR:",
            type(e).__name__,
            str(e)
        )


async def on_comment(event):

    try:

        user = getattr(
            event,
            "user",
            None
        )

        username = get_username(user)

        comment = (
            getattr(
                event,
                "comment",
                ""
            )
            or ""
        )

        await broadcast({

            "type":
                "comment",

            "username":
                username,

            "comment":
                comment

        })

    except Exception as e:

        print(
            "[Comment] ERROR:",
            type(e).__name__,
            str(e)
        )


# ============================================================
# STOP TIKTOK
# ============================================================

async def stop_tiktok():

    global tiktok_client
    global tiktok_task
    global current_room_id

    if tiktok_client is not None:

        try:

            result = tiktok_client.disconnect()

            if asyncio.iscoroutine(result):

                await result

        except Exception as e:

            print(
                "[TikTok] disconnect error:",
                type(e).__name__,
                str(e)
            )

    if tiktok_task is not None:

        try:

            if not tiktok_task.done():

                tiktok_task.cancel()

        except Exception:
            pass

    tiktok_client = None
    tiktok_task = None
    current_room_id = None


# ============================================================
# START TIKTOK
# ============================================================

async def start_tiktok(username: str):

    global tiktok_client
    global tiktok_task
    global current_user
    global current_room_id

    if not TIKTOK_AVAILABLE:

        await broadcast({

            "type":
                "status",

            "message":
                "TikTokLive import edilmedi.",

            "connected":
                False

        })

        return

    username = (
        username
        or ""
    ).strip().lstrip("@")

    if not username:

        await broadcast({

            "type":
                "status",

            "message":
                "Username boşdur",

            "connected":
                False

        })

        return

    await stop_tiktok()

    current_user = username

    await broadcast({

        "type":
            "status",

        "message":
            f"Yoxlanılır @{username} ...",

        "connected":
            False,

        "username":
            username

    })

    print(
        f"[TikTok] is_live @{username}"
    )

    try:

        client = TikTokLiveClient(
            unique_id=username
        )

    except Exception as e:

        print(
            "[TikTok] client creation ERROR:",
            type(e).__name__,
            str(e)
        )

        await broadcast({

            "type":
                "status",

            "message":
                f"Client xətası: {str(e)[:200]}",

            "connected":
                False

        })

        return

    # --------------------------------------------------------
    # LIVE CHECK
    # --------------------------------------------------------

    try:

        is_live = await client.is_live()

    except Exception as e:

        error = str(e)

        print(
            "[TikTok] is_live ERROR:",
            type(e).__name__,
            error
        )

        await broadcast({

            "type":
                "status",

            "message":
                f"LIVE yoxlama xətası: {error[:200]}",

            "connected":
                False,

            "error":
                error

        })

        return

    if not is_live:

        await broadcast({

            "type":
                "status",

            "message":
                f"@{username} hazırda LIVE deyil",

            "connected":
                False,

            "username":
                username

        })

        return

    # --------------------------------------------------------
    # ROOM ID
    # --------------------------------------------------------

    room_id = getattr(
        client,
        "room_id",
        None
    )

    if room_id is None:

        room_id = getattr(
            client,
            "roomId",
            None
        )

    print(
        "[TikTok] room_id:",
        room_id
    )

    await broadcast({

        "type":
            "status",

        "message":
            f"LIVE tapıldı, qoşulur @{username} ...",

        "connected":
            False,

        "username":
            username,

        "room_id":
            room_id

    })

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    try:

        client.add_listener(
            ConnectEvent,
            on_connect
        )

        client.add_listener(
            DisconnectEvent,
            on_disconnect
        )

        client.add_listener(
            GiftEvent,
            on_gift
        )

        client.add_listener(
            LikeEvent,
            on_like
        )

        client.add_listener(
            FollowEvent,
            on_follow
        )

        client.add_listener(
            ShareEvent,
            on_share
        )

        client.add_listener(
            CommentEvent,
            on_comment
        )

    except Exception as e:

        print(
            "[TikTok] event registration ERROR:",
            type(e).__name__,
            str(e)
        )

        await broadcast({

            "type":
                "status",

            "message":
                f"Event xətası: {str(e)[:200]}",

            "connected":
                False

        })

        return

    tiktok_client = client
    current_room_id = room_id

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    try:

        result = await client.start(
            fetch_live_check=False,
            fetch_gift_info=True
        )

        tiktok_task = result

        print(
            f"[TikTok] START OK @{username}"
        )

    except Exception as e:

        error = str(e)

        print(
            "[TikTok] START ERROR:",
            type(e).__name__,
            error
        )

        tiktok_client = None
        tiktok_task = None

        await broadcast({

            "type":
                "status",

            "message":
                f"Qoşulma xətası: {error[:250]}",

            "connected":
                False,

            "error":
                error

        })


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
        "WS client +1 =",
        len(clients)
    )

    await ws.send_str(
        json.dumps(
            {
                "type":
                    "init",

                "scores":
                    scores[:],

                "total_likes":
                    total_likes,

                "supporters":
                    [
                        {
                            "username":
                                username,

                            "coins":
                                coins
                        }

                        for username, coins
                        in sorted(
                            supporters.items(),
                            key=lambda item: -item[1]
                        )[:3]
                    ],

                "gift_map":
                    GIFT_MAP,

                "connected":
                    tiktok_client is not None,

                "username":
                    current_user,

                "room_id":
                    current_room_id
            },
            ensure_ascii=False
        )
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

            message_type = data.get(
                "type"
            )

            # ------------------------------------------------
            # SET USER
            # ------------------------------------------------

            if message_type == "set_user":

                username = (
                    data.get(
                        "username"
                    )
                    or ""
                ).strip().lstrip("@")

                if username:

                    asyncio.create_task(
                        start_tiktok(
                            username
                        )
                    )

                else:

                    await stop_tiktok()

                    await broadcast({

                        "type":
                            "status",

                        "message":
                            "Test rejimi",

                        "connected":
                            False

                    })

            # ------------------------------------------------
            # TEST GIFT
            # ------------------------------------------------

            elif message_type == "gift":

                try:

                    player_id = (
                        int(
                            data.get(
                                "player_id",
                                0
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
                            GIFT_POINTS
                        )
                    )

                except Exception:

                    points = GIFT_POINTS

                username = (
                    data.get(
                        "username",
                        "test"
                    )
                    or "test"
                )

                gift_name = (
                    data.get(
                        "gift_name",
                        "Test"
                    )
                    or "Test"
                )

                try:

                    coins = int(
                        data.get(
                            "coins",
                            1
                        )
                    )

                except Exception:

                    coins = 1

                supporters[username] = (
                    supporters.get(
                        username,
                        0
                    )
                    + coins
                )

                scores[player_id] += points

                await broadcast({

                    "type":
                        "gift",

                    "username":
                        username,

                    "player_name":
                        username,

                    "gift_name":
                        gift_name,

                    "player_id":
                        player_id,

                    "points":
                        points,

                    "coins":
                        coins,

                    "count":
                        1,

                    "scores":
                        scores[:],

                    "avatar":
                        "",

                    "sound":
                        True

                })

                await broadcast_top()

            # ------------------------------------------------
            # RESET
            # ------------------------------------------------

            elif message_type == "reset_scores":

                for i in range(
                    PLAYER_COUNT
                ):
                    scores[i] = 0

                total_likes = 0
                like_points_given = 0

                supporters.clear()

                await broadcast_scores()
                await broadcast_top()

    except Exception as e:

        print(
            "[WS] ERROR:",
            type(e).__name__,
            str(e)
        )

    finally:

        clients.discard(ws)

        print(
            "WS client -1 =",
            len(clients)
        )

    return ws


# ============================================================
# HTTP
# ============================================================

async def index(request):

    files = (
        "football_gift_race_fixed.html",
        "index.html",
    )

    for filename in files:

        path = ROOT / filename

        if path.is_file():

            response = web.FileResponse(
                path
            )

            response.headers[
                "Cache-Control"
            ] = (
                "no-store, "
                "no-cache, "
                "must-revalidate, "
                "max-age=0"
            )

            response.headers[
                "Pragma"
            ] = "no-cache"

            return response

    return web.Response(

        text=
            "index.html not found",

        status=404

    )


# ============================================================
# APP
# ============================================================

def create_app():

    app = web.Application()

    app.router.add_get(
        "/",
        index
    )

    app.router.add_get(
        "/ws",
        ws_handler
    )

    app.router.add_get(
        "/index.html",
        index
    )

    app.router.add_get(
        "/football_gift_race_fixed.html",
        index
    )

    assets = ROOT / "assets"

    if assets.is_dir():

        app.router.add_static(
            "/assets/",
            assets
        )

    return app


# ============================================================
# MAIN SERVER
# ============================================================

async def main():

    app = create_app()

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        HOST,
        PORT
    )

    await site.start()

    print("=" * 70)
    print(" Football Gift Race + TikTok Live")
    print(f" http://localhost:{PORT}")
    print("=" * 70)

    print(
        "[Status] TikTokLive:",
        "OK"
        if TIKTOK_AVAILABLE
        else "UNAVAILABLE"
    )

    print(
        "[Status] Euler:",
        "used internally by TikTokLive"
    )

    while True:

        await asyncio.sleep(
            3600
        )


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "Stopped."
        )
#!/usr/bin/env python3
"""
Football Gift Race — TikTok Live server
Termux / Android ready

TikTokLive + EulerApiSdk
"""

from __future__ import annotations

import asyncio
import json
import inspect
from pathlib import Path

from aiohttp import web
import aiohttp


# ============================================================
# EulerApiSdk
# ============================================================

EULER_AVAILABLE = False

euler_fetch_webcast_url = None
EulerClient = None
EulerAuthenticatedClient = None


def prepare_euler_sdk():
    """
    EulerApiSdk üçün düzgün import.

    IMPORTANT:
        EulerApiSdk.api.tik_tok_live_rooms.fetch_webcast_url
    bir FUNCTION deyil, MODULE-dur.

    Əsl async function:
        EulerApiSdk.api.tik_tok_live_rooms.fetch_webcast_url.asyncio
    """

    global euler_fetch_webcast_url
    global EulerClient
    global EulerAuthenticatedClient

    try:

        # ----------------------------------------------------
        # DÜZGÜN endpoint
        # ----------------------------------------------------

        from EulerApiSdk.api.tik_tok_live_rooms.fetch_webcast_url import (
            asyncio as fetch_webcast_url_async
        )

        euler_fetch_webcast_url = (
            fetch_webcast_url_async
        )

        # ----------------------------------------------------
        # Euler client
        # ----------------------------------------------------

        from EulerApiSdk.client import (
            Client,
            AuthenticatedClient,
        )

        EulerClient = Client
        EulerAuthenticatedClient = AuthenticatedClient

        print()
        print("=" * 70)
        print("[Euler] SDK IMPORT OK")
        print("=" * 70)

        print(
            "[Euler] fetch_webcast_url:",
            euler_fetch_webcast_url
        )

        print(
            "[Euler] module:",
            getattr(
                euler_fetch_webcast_url,
                "__module__",
                "unknown"
            )
        )

        try:

            print(
                "[Euler] signature:",
                inspect.signature(
                    euler_fetch_webcast_url
                )
            )

        except Exception as e:

            print(
                "[Euler] signature error:",
                type(e).__name__,
                str(e)
            )

        print(
            "[Euler] Client:",
            EulerClient
        )

        print(
            "[Euler] AuthenticatedClient:",
            EulerAuthenticatedClient
        )

        print("=" * 70)

        return True

    except Exception as e:

        print()
        print("=" * 70)

        print(
            "[Euler] IMPORT FAILED:",
            type(e).__name__,
            str(e)
        )

        print("=" * 70)

        euler_fetch_webcast_url = None
        EulerClient = None
        EulerAuthenticatedClient = None

        return False


EULER_AVAILABLE = prepare_euler_sdk()


# ============================================================
# Euler helper
# ============================================================

async def euler_fetch_room(
    room_id: str,
    unique_id: str | None = None
):
    """
    Euler üzerinden TikTok LIVE room websocket məlumatını alır.

    Endpoint:
        GET /webcast/rooms/{room_id}/connect

    Euler SDK-nın göstərdiyi real signature istifadə olunur.
    """

    if not EULER_AVAILABLE:

        raise RuntimeError(
            "EulerApiSdk available deyil"
        )

    if not room_id:

        raise ValueError(
            "room_id boşdur"
        )

    if EulerClient is None:

        raise RuntimeError(
            "Euler Client import olunmayıb"
        )

    print(
        "[Euler] Fetching room:",
        room_id
    )

    # --------------------------------------------------------
    # Anonymous Euler client
    # --------------------------------------------------------

    client = EulerClient(
        base_url="https://eulerstream.com"
    )

    try:

        result = await euler_fetch_webcast_url(
            room_id=str(room_id),
            client=client,
            unique_id=unique_id
        )

        print(
            "[Euler] fetch_webcast_url result:",
            result
        )

        return result

    finally:

        # Client obyektində close varsa bağlayırıq.
        try:

            close = getattr(
                client,
                "close",
                None
            )

            if callable(close):

                result = close()

                if inspect.isawaitable(result):

                    await result

        except Exception as e:

            print(
                "[Euler] client close:",
                type(e).__name__,
                str(e)
            )


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

    print(
        "[TikTokLive] import OK"
    )

except Exception as e:

    TIKTOK_AVAILABLE = False

    print(
        "[TikTokLive import failed]",
        type(e).__name__,
        ":",
        str(e)
    )


# ============================================================
# SERVER
# ============================================================

HOST = "0.0.0.0"
PORT = 8000

PLAYER_COUNT = 7


# ============================================================
# Gift mapping
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
# State
# ============================================================

clients = set()

total_likes = 0

like_points_given = 0

supporters = {}

scores = [0] * PLAYER_COUNT

tiktok_client = None

tiktok_task = None

current_user = ""

current_room_id = None

ROOT = Path(__file__).parent.resolve()


# ============================================================
# Broadcast
# ============================================================

async def broadcast(data: dict):

    if not clients:
        return

    msg = json.dumps(
        data,
        ensure_ascii=False
    )

    dead = []

    for ws in list(clients):

        try:

            await ws.send_str(msg)

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
        key=lambda x: x[1],
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
# Avatar
# ============================================================

_avatar_debug_done = False


def _extract_avatar(user) -> str | None:

    global _avatar_debug_done

    if user is None:

        return None

    found = []

    def walk(obj, depth=0):

        if obj is None or depth > 5:

            return

        if isinstance(obj, str):

            if (
                obj.startswith("http")
                and (
                    "tiktok" in obj
                    or "byteoversea" in obj
                    or "avt" in obj
                    or "avatar" in obj
                    or "webp" in obj
                    or "jpeg" in obj
                    or "png" in obj
                )
            ):

                found.append(obj)

            return

        if isinstance(obj, (list, tuple)):

            for x in obj[:8]:

                walk(
                    x,
                    depth + 1
                )

            return

        if isinstance(obj, dict):

            for v in obj.values():

                walk(
                    v,
                    depth + 1
                )

            return

        for method_name in (
            "model_dump",
            "dict",
            "as_dict",
            "to_dict"
        ):

            fn = getattr(
                obj,
                method_name,
                None
            )

            if callable(fn):

                try:

                    walk(
                        fn(),
                        depth + 1
                    )

                    return

                except Exception:

                    pass

        d = getattr(
            obj,
            "__dict__",
            None
        )

        if isinstance(d, dict):

            for v in d.values():

                walk(
                    v,
                    depth + 1
                )

        for attr in (
            "url_list",
            "urlList",
            "urls",
            "url",
            "uri",
            "avatar_thumb",
            "avatar_medium",
            "avatar",
            "profile_picture"
        ):

            try:

                walk(
                    getattr(
                        obj,
                        attr,
                        None
                    ),
                    depth + 1
                )

            except Exception:

                pass

    walk(user)

    for url in found:

        if (
            isinstance(url, str)
            and url.startswith("http")
        ):

            return url

    if not _avatar_debug_done:

        _avatar_debug_done = True

        try:

            print(
                "[Avatar debug] attrs:",
                [
                    a
                    for a in dir(user)
                    if (
                        "avatar" in a.lower()
                        or "profile" in a.lower()
                        or "pic" in a.lower()
                    )
                ]
            )

            print(
                "[Avatar debug] found:",
                found[:3]
            )

        except Exception as e:

            print(
                "[Avatar debug]",
                e
            )

    return None


# ============================================================
# TikTok Events
# ============================================================

async def on_connect(event):

    room_id = getattr(
        tiktok_client,
        "room_id",
        None
    )

    unique_id = getattr(
        event,
        "unique_id",
        current_user
    )

    print(
        f"[TikTok] LIVE connected "
        f"@{unique_id} "
        f"room={room_id}"
    )

    await broadcast({

        "type": "status",

        "message":
            f"LIVE @{unique_id}",

        "connected": True,

        "username": unique_id,

        "room_id": room_id
    })


async def on_disconnect(event):

    print(
        "[TikTok] Disconnected"
    )

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

        username = "user"

        avatar = None

        if user is not None:

            username = (

                getattr(
                    user,
                    "nickname",
                    None
                )

                or getattr(
                    user,
                    "unique_id",
                    None
                )

                or "user"

            )

            avatar = _extract_avatar(
                user
            )

        gift_name = (

            getattr(
                gift,
                "name",
                None
            )

            or "?"

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

            repeat_end = (

                int(repeat_end)

                if repeat_end is not None

                else 0

            )

        except Exception:

            repeat_end = (

                1

                if repeat_end

                else 0

            )

        is_mid_streak = (

            streakable

            and streaking

            and not repeat_end

        )

        if is_mid_streak:

            return

        print(
            f"[Gift] {username} "
            f"→ {gift_name} "
            f"x{count} "
            f"({coins}💎)"
        )

        supporters[username] = (

            supporters.get(
                username,
                0
            )

            + coins * count

        )

        key = gift_name.lower().strip()

        player_id = GIFT_MAP.get(
            key
        )

        if player_id is None:

            for k, pid in GIFT_MAP.items():

                if (
                    k in key
                    or key in k
                ):

                    player_id = pid

                    break

        if player_id is None:

            player_id = (

                abs(
                    hash(username)
                )

                % PLAYER_COUNT

            )

        points = (

            GIFT_POINTS

            * max(
                1,
                count
            )

        )

        scores[player_id] += points

        await broadcast({

            "type": "gift",

            "username": username,

            "player_name": username,

            "gift_name": gift_name,

            "gift_key": key,

            "coins": coins,

            "count": count,

            "player_id": player_id,

            "points": points,

            "scores": scores[:],

            "avatar":
                avatar or "",

            "sound": True
        })

        await broadcast_top()

    except Exception as e:

        print(
            "[Gift] error:",
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

            room_total = (

                int(room_total)

                if room_total is not None

                else total_likes

            )

        except Exception:

            room_total = total_likes

        user = getattr(
            event,
            "user",
            None
        )

        username = "user"

        avatar = None

        if user is not None:

            username = (

                getattr(
                    user,
                    "nickname",
                    None
                )

                or getattr(
                    user,
                    "unique_id",
                    None
                )

                or "user"

            )

            avatar = _extract_avatar(
                user
            )

        await broadcast({

            "type": "like",

            "amount": amount,

            "total": room_total,

            "username": username
        })

        should_have = (

            total_likes
            // LIKE_EVERY

        )

        new_points = (

            should_have
            - like_points_given

        )

        if new_points > 0:

            like_points_given = (
                should_have
            )

            scores[
                AZERBAIJAN_PLAYER
            ] += (

                new_points
                * LIKE_POINTS

            )

            await broadcast({

                "type": "gift",

                "username": username,

                "player_name": username,

                "gift_name": "Like",

                "gift_key": "like",

                "coins": 0,

                "count": new_points,

                "player_id":
                    AZERBAIJAN_PLAYER,

                "points":
                    new_points * LIKE_POINTS,

                "scores": scores[:],

                "avatar":
                    avatar or "",

                "sound": True,

                "reason": "like"
            })

            await broadcast_top()

    except Exception as e:

        print(
            "[Like] error:",
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

        username = "user"

        avatar = None

        if user is not None:

            username = (

                getattr(
                    user,
                    "nickname",
                    None
                )

                or getattr(
                    user,
                    "unique_id",
                    None
                )

                or "user"

            )

            avatar = _extract_avatar(
                user
            )

        pid = TURKEY_PLAYER

        scores[pid] += FOLLOW_POINTS

        await broadcast({

            "type": "follow",

            "username": username

        })

        await broadcast({

            "type": "gift",

            "username": username,

            "player_name": username,

            "gift_name": "Follow",

            "gift_key": "follow",

            "coins": 0,

            "count": 1,

            "player_id": pid,

            "points": FOLLOW_POINTS,

            "scores": scores[:],

            "avatar":
                avatar or "",

            "sound": True,

            "reason": "follow"

        })

        await broadcast_top()

    except Exception as e:

        print(
            "[Follow] error:",
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

        username = "user"

        if user is not None:

            username = (

                getattr(
                    user,
                    "nickname",
                    None
                )

                or getattr(
                    user,
                    "unique_id",
                    None
                )

                or "user"

            )

        await broadcast({

            "type": "share",

            "username": username

        })

    except Exception as e:

        print(
            "[Share] error:",
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

        username = "user"

        if user is not None:

            username = (

                getattr(
                    user,
                    "nickname",
                    None
                )

                or getattr(
                    user,
                    "unique_id",
                    None
                )

                or "user"

            )

        await broadcast({

            "type": "comment",

            "username": username,

            "comment":

                getattr(
                    event,
                    "comment",
                    ""
                )

                or ""

        })

    except Exception as e:

        print(
            "[Comment] error:",
            type(e).__name__,
            str(e)
        )


# ============================================================
# TikTok connection
# ============================================================

async def stop_tiktok():

    global tiktok_client
    global tiktok_task
    global current_room_id

    if tiktok_client is not None:

        try:

            await tiktok_client.disconnect()

        except Exception as e:

            print(
                "[TikTok] disconnect:",
                e
            )

    tiktok_client = None

    tiktok_task = None

    current_room_id = None


async def start_tiktok(username: str):

    global tiktok_client
    global tiktok_task
    global current_user
    global current_room_id

    if not TIKTOK_AVAILABLE:

        await broadcast({

            "type": "status",

            "message":
                "TikTokLive import edilemedi.",

            "connected": False

        })

        return

    username = (

        username or ""

    ).strip().lstrip("@")

    if not username:

        await broadcast({

            "type": "status",

            "message":
                "Username boşdur",

            "connected": False

        })

        return

    await stop_tiktok()

    current_user = username

    await broadcast({

        "type": "status",

        "message":
            f"Yoxlanılır @{username} ...",

        "connected": False

    })

    print(
        f"[TikTok] Checking is_live @{username}"
    )

    client = TikTokLiveClient(
        unique_id=username
    )

    # --------------------------------------------------------
    # is_live
    # --------------------------------------------------------

    try:

        is_live = await client.is_live()

    except Exception as e:

        error = str(e)

        print(
            "[TikTok] is_live error:",
            type(e).__name__,
            error
        )

        await broadcast({

            "type": "status",

            "message":
                f"Yoxlama xətası: "
                f"{error[:150]}",

            "connected": False,

            "error": error

        })

        return

    if not is_live:

        await broadcast({

            "type": "status",

            "message":
                f"@{username} "
                f"hazırda LIVE deyil",

            "connected": False

        })

        return

    # --------------------------------------------------------
    # Room ID almağa çalış
    # --------------------------------------------------------

    room_id = getattr(
        client,
        "room_id",
        None
    )

    if room_id is None:

        try:

            room_id = getattr(
                client,
                "roomId",
                None
            )

        except Exception:

            room_id = None

    print(
        "[TikTok] room_id:",
        room_id
    )

    # --------------------------------------------------------
    # Euler test
    # --------------------------------------------------------

    if EULER_AVAILABLE and room_id:

        try:

            print(
                "[Euler] Trying "
                "fetch_webcast_url..."
            )

            euler_result = (
                await euler_fetch_room(
                    room_id=str(room_id),
                    unique_id=username
                )
            )

            print(
                "[Euler] SUCCESS:"
            )

            print(
                euler_result
            )

            await broadcast({

                "type": "euler",

                "success": True,

                "room_id":
                    str(room_id)

            })

        except Exception as e:

            print(
                "[Euler] fetch failed:",
                type(e).__name__,
                str(e)
            )

            await broadcast({

                "type": "euler",

                "success": False,

                "error":
                    str(e)[:300],

                "room_id":
                    str(room_id)

            })

    elif EULER_AVAILABLE:

        print(
            "[Euler] room_id TikTokLive "
            "client-dan alınmadı"
        )

    await broadcast({

        "type": "status",

        "message":
            f"LIVE tapıldı, "
            f"qoşulur @{username} ...",

        "connected": False

    })

    # --------------------------------------------------------
    # Events
    # --------------------------------------------------------

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

    tiktok_client = client

    current_room_id = room_id

    # --------------------------------------------------------
    # TikTokLive start
    # --------------------------------------------------------

    try:

        task = await client.start(
            fetch_live_check=False,
            fetch_gift_info=True
        )

        tiktok_task = task

        print(
            f"[TikTok] start() OK @{username}"
        )

    except Exception as e:

        error = str(e)

        print(
            "[TikTok] start/connect failed:",
            type(e).__name__,
            error
        )

        tiktok_client = None

        tiktok_task = None

        await broadcast({

            "type": "status",

            "message":
                f"Qoşulma xətası: "
                f"{error[:150]}",

            "connected": False,

            "error": error

        })


# ============================================================
# WebSocket
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
        json.dumps({

            "type": "init",

            "scores": scores[:],

            "total_likes":
                total_likes,

            "supporters": [

                {
                    "username": username,
                    "coins": coins
                }

                for username, coins
                in sorted(
                    supporters.items(),
                    key=lambda x: -x[1]
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
        ensure_ascii=False)
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

                        "type": "status",

                        "message":
                            "Test rejimi",

                        "connected": False

                    })

            elif message_type == "gift":

                try:

                    pid = (

                        int(
                            data.get(
                                "player_id",
                                0
                            )
                        )

                        % PLAYER_COUNT

                    )

                except Exception:

                    pid = 0

                try:

                    points = int(
                        data.get(
                            "points",
                            GIFT_POINTS
                        )
                    )

                except Exception:

                    points = GIFT_POINTS

                username = data.get(
                    "username",
                    "test"
                )

                gift_name = data.get(
                    "gift_name",
                    "Test"
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

                scores[pid] += points

                await broadcast({

                    "type": "gift",

                    "username":
                        username,

                    "gift_name":
                        gift_name,

                    "player_id":
                        pid,

                    "points":
                        points,

                    "coins":
                        coins,

                    "scores":
                        scores[:],

                    "player_name":
                        username,

                    "sound": True

                })

                await broadcast_top()

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

    for filename in (

        "football_gift_race_fixed.html",

        "index.html"

    ):

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
            "football_gift_race_fixed.html "
            "not found",

        status=404

    )


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
# Main
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

    print("=" * 50)

    print(
        " Football Gift Race + TikTok Live"
    )

    print(
        f" http://localhost:{PORT}"
    )

    print("=" * 50)

    print(
        "[Status] EulerApiSdk:",
        "OK"
        if EULER_AVAILABLE
        else "UNAVAILABLE"
    )

    print(
        "[Status] TikTokLive:",
        "OK"
        if TIKTOK_AVAILABLE
        else "UNAVAILABLE"
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
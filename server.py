#!/usr/bin/env python3
"""
Football Gift Race — TikTok Live server
Termux / Android ready
"""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

from aiohttp import web
import aiohttp


# ============================================================
# TikTokLive / EulerApiSdk compatibility
# ============================================================
#
# TikTokLive 6.6.6 kendi içinde:
#
# from EulerApiSdk.api.tik_tok_live import fetch_webcast_url
#
# kullanıyor.
#
# Bazı Android/p4a paketlemelerinde EulerApiSdk'nin
# tik_tok_live/__init__.py içindeki export eksik kalabiliyor.
#
# Gerçek fetch_webcast_url alt modülünü bulup pakete bağlıyoruz.
# SAHTE / dummy fonksiyon kullanılmıyor.
# ============================================================

def prepare_euler_sdk():
    try:
        import EulerApiSdk
        import EulerApiSdk.api.tik_tok_live as ttl

        print("[Euler] EulerApiSdk:", getattr(EulerApiSdk, "__version__", "unknown"))
        print("[Euler] module:", getattr(ttl, "__file__", "unknown"))

        # Normal durumda zaten mevcut.
        if hasattr(ttl, "fetch_webcast_url"):
            print("[Euler] fetch_webcast_url: OK")
            return True

        print("[Euler] fetch_webcast_url __init__ içinde yok")
        print("[Euler] Alt modül yüklenmeye çalışılıyor...")

        # Generated SDK'da gerçek endpoint modülü.
        endpoint = importlib.import_module(
            "EulerApiSdk.api.tik_tok_live.fetch_webcast_url"
        )

        fetch_func = getattr(endpoint, "fetch_webcast_url", None)

        if fetch_func is None:
            raise ImportError(
                "EulerApiSdk.api.tik_tok_live.fetch_webcast_url "
                "modülü bulundu fakat fetch_webcast_url yok."
            )

        # TikTokLive'in beklediği export'u oluştur.
        ttl.fetch_webcast_url = fetch_func

        print("[Euler] fetch_webcast_url export düzeltildi")
        return True

    except Exception as e:
        print(
            "[Euler] CRITICAL:",
            type(e).__name__,
            str(e)
        )

        try:
            import EulerApiSdk.api.tik_tok_live as ttl
            print(
                "[Euler] tik_tok_live attrs:",
                [
                    x for x in dir(ttl)
                    if not x.startswith("_")
                ]
            )
        except Exception as e2:
            print(
                "[Euler] module inspect failed:",
                type(e2).__name__,
                str(e2)
            )

        return False


EULER_AVAILABLE = prepare_euler_sdk()


# ============================================================
# TikTokLive
# ============================================================

try:
    if not EULER_AVAILABLE:
        raise ImportError(
            "EulerApiSdk fetch_webcast_url hazırlanamadı."
        )

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

    print("[TikTokLive] import OK")

except Exception as _tiktok_import_error:

    TIKTOK_AVAILABLE = False

    TikTokLiveClient = None

    ConnectEvent = None
    DisconnectEvent = None
    GiftEvent = None
    LikeEvent = None
    FollowEvent = None
    ShareEvent = None
    CommentEvent = None

    print(
        "[TikTokLive import failed]",
        type(_tiktok_import_error).__name__,
        ":",
        str(_tiktok_import_error)
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

    # 0 NƏRİMAN — Azerbaycan — Rose
    "rose": 0,
    "gül": 0,
    "gul": 0,
    "my first rose": 0,
    "rosa": 0,

    # 1 ARDA — Türkiye — TikTok
    "tiktok": 1,

    # 2 GOLOVIN — Rusya — Flame Heart
    "flame heart": 2,
    "flameheart": 2,
    "flame": 2,

    # 3 CHHETRI — Hindistan — GG
    "gg": 3,

    # 4 PULISIC — ABD — Ice Cream
    "ice cream cone": 4,
    "ice cream": 4,
    "icecream": 4,
    "dondurma": 4,

    # 5 MESSI — Arjantin — Football
    "football": 5,
    "futbol": 5,
    "soccer": 5,
    "soccer ball": 5,

    # 6 RONALDO — Portekiz — Heart Puff
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
                "username": u,
                "coins": c
            }
            for u, c in top
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
                walk(x, depth + 1)

            return

        if isinstance(obj, dict):

            for v in obj.values():
                walk(v, depth + 1)

            return

        for meth in (
            "model_dump",
            "dict",
            "as_dict",
            "to_dict"
        ):

            fn = getattr(obj, meth, None)

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
                walk(v, depth + 1)

        for a in (
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
                    getattr(obj, a, None),
                    depth + 1
                )

            except Exception:
                pass

    walk(user)

    for u in found:

        if (
            isinstance(u, str)
            and u.startswith("http")
        ):
            return u

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
                "[Avatar debug] found urls:",
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

async def on_connect(event: ConnectEvent):

    room_id = getattr(
        tiktok_client,
        "room_id",
        None
    )

    print(
        f"[TikTok] LIVE connected "
        f"@{event.unique_id} "
        f"room={room_id}"
    )

    await broadcast({
        "type": "status",
        "message": f"LIVE @{event.unique_id}",
        "connected": True,
        "username": event.unique_id
    })


async def on_disconnect(event: DisconnectEvent):

    print(
        "[TikTok] Disconnected"
    )

    await broadcast({
        "type": "status",
        "message": "TikTok disconnected",
        "connected": False
    })


async def on_gift(event: GiftEvent):

    try:

        gift = getattr(
            event,
            "gift",
            None
        )

        if gift is None:
            return

        username = "user"

        avatar = None

        user = getattr(
            event,
            "user",
            None
        )

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

        streak_tag = (
            " [streak]"
            if is_mid_streak
            else (
                " [end]"
                if (
                    streakable
                    and not streaking
                )
                else ""
            )
        )

        print(
            f"[Gift] {username} "
            f"→ {gift_name} "
            f"x{count}"
            f"{streak_tag} "
            f"({coins}💎)"
        )

        if is_mid_streak:
            return

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
                abs(hash(username))
                % PLAYER_COUNT
            )

        points = (
            GIFT_POINTS
            * max(1, count)
        )

        scores[player_id] += points

        print(
            f"       → P{player_id} "
            f"(+{points}) "
            f"score={scores[player_id]} "
            f"AD={username}"
            + (
                " AVATAR=ok"
                if avatar
                else " AVATAR=yox"
            )
            + f" gift={gift_name!r}"
        )

        payload = {

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

            "avatar": avatar or "",

            "sound": True
        }

        await broadcast(
            payload
        )

        await broadcast_top()

    except Exception as e:

        print(
            "Gift error:",
            e
        )


async def on_like(event: LikeEvent):

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

            amount = (
                int(amount)
                if amount is not None
                else 1
            )

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

        username = "user"

        avatar = None

        user = getattr(
            event,
            "user",
            None
        )

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

            print(
                f"[Like] {username} "
                f"→ {total_likes} like "
                f"→ Azerbaycan "
                f"+{new_points} puan "
                f"(toplam: "
                f"{scores[AZERBAIJAN_PLAYER]})"
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
            e
        )


async def on_follow(event: FollowEvent):

    try:

        username = "user"

        avatar = None

        user = getattr(
            event,
            "user",
            None
        )

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

        print(
            f"[Follow] @{username} "
            f"→ Türkiye "
            f"+{FOLLOW_POINTS} puan "
            f"(toplam: {scores[pid]})"
        )

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
            "Follow error:",
            e
        )


async def on_share(event: ShareEvent):

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
            "Share error:",
            e
        )


async def on_comment(event: CommentEvent):

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
            "Comment error:",
            e
        )


# ============================================================
# TikTok connection
# ============================================================

async def stop_tiktok():

    global tiktok_client
    global tiktok_task

    if tiktok_client:

        try:

            await tiktok_client.disconnect()

        except Exception:

            try:

                await tiktok_client.stop()

            except Exception:
                pass

        tiktok_client = None

    tiktok_task = None


async def start_tiktok(username: str):

    global tiktok_client
    global tiktok_task
    global current_user

    if not TIKTOK_AVAILABLE:

        await broadcast({

            "type": "status",

            "message":
                "TikTokLive quraşdırılmayıb.",

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
        f"[TikTok] Checking is_live "
        f"@{username} ..."
    )

    client = TikTokLiveClient(
        unique_id=f"@{username}"
    )

    try:

        is_live = await client.is_live()

    except Exception as e:

        err = str(e)

        print(
            f"[TikTok] is_live error: "
            f"{err}"
        )

        await broadcast({

            "type": "status",

            "message":
                f"Yoxlama xətası: "
                f"{err[:120]}",

            "connected": False,

            "error": err
        })

        return

    if not is_live:

        print(
            f"[TikTok] @{username} "
            f"is NOT live"
        )

        await broadcast({

            "type": "status",

            "message":
                f"@{username} "
                f"hazırda LIVE deyil",

            "connected": False
        })

        return

    print(
        f"[TikTok] @{username} "
        f"IS LIVE — connecting ..."
    )

    await broadcast({

        "type": "status",

        "message":
            f"LIVE tapıldı, "
            f"qoşulur @{username} ...",

        "connected": False
    })

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

    try:

        task = await client.start(
            fetch_live_check=False,
            fetch_gift_info=True
        )

        tiktok_task = task

        print(
            f"[TikTok] start() OK "
            f"@{username}"
        )

    except Exception as e:

        err = str(e)

        print(
            f"[TikTok] start/connect failed: "
            f"{err}"
        )

        tiktok_client = None

        await broadcast({

            "type": "status",

            "message":
                f"Qoşulma xətası: "
                f"{err[:140]}",

            "connected": False,

            "error": err
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
                    "username": u,
                    "coins": c
                }
                for u, c
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
                current_user

        })
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

            t = data.get(
                "type"
            )

            if t == "set_user":

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

            elif t == "gift":

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

            elif t == "reset_scores":

                for i in range(
                    PLAYER_COUNT
                ):

                    scores[i] = 0

                total_likes = 0

                like_points_given = 0

                await broadcast_scores()

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

    for name in (
        "football_gift_race_fixed.html",
        "index.html"
    ):

        p = ROOT / name

        if p.is_file():

            resp = web.FileResponse(
                p
            )

            resp.headers[
                "Cache-Control"
            ] = (
                "no-store, "
                "no-cache, "
                "must-revalidate, "
                "max-age=0"
            )

            resp.headers[
                "Pragma"
            ] = "no-cache"

            return resp

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

    if (
        ROOT / "assets"
    ).is_dir():

        app.router.add_static(
            "/assets/",
            ROOT / "assets"
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

    if not EULER_AVAILABLE:

        print(
            " WARNING: EulerApiSdk "
            "fetch_webcast_url unavailable"
        )

    if not TIKTOK_AVAILABLE:

        print(
            " WARNING: TikTokLive not installed"
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
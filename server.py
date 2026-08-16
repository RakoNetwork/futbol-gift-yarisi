#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiohttp
from aiohttp import web

TIKTOK_AVAILABLE = False
TikTokLiveClient = None
ConnectEvent = DisconnectEvent = GiftEvent = LikeEvent = FollowEvent = None
WebDefaults = None

try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import (
        ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, FollowEvent,
    )
    from TikTokLive.client.web.web_settings import WebDefaults
    TIKTOK_AVAILABLE = True
    print("[TikTokLive] IMPORT OK")
except Exception as exc:
    print("[TikTokLive] IMPORT FAILED:", type(exc).__name__, str(exc))

HOST = "0.0.0.0"
PORT = 8000
PLAYER_COUNT = 7
ROOT = Path(__file__).resolve().parent

GIFT_POINTS = 1
FOLLOW_POINTS = 2
LIKE_POINTS = 1
LIKE_EVERY = 20

GIFT_MAP = {
    "rose": 0, "gül": 0, "gul": 0, "my first rose": 0, "rosa": 0,
    "tiktok": 1,
    "flame heart": 2, "flameheart": 2, "flame": 2,
    "gg": 3,
    "ice cream cone": 4, "ice cream": 4, "icecream": 4, "dondurma": 4,
    "football": 5, "futbol": 5, "soccer": 5, "soccer ball": 5,
    "heart puff": 6, "heartpuff": 6,
}

clients: set[web.WebSocketResponse] = set()
scores = [0] * PLAYER_COUNT
supporters: dict[str, int] = {}
total_likes = 0
like_points_given = 0
tiktok_client = None
current_user = ""
current_api_key = ""


async def broadcast(data: dict) -> None:
    if not clients:
        return
    message = json.dumps(data, ensure_ascii=False)
    dead = []
    for ws in list(clients):
        try:
            await ws.send_str(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def broadcast_scores() -> None:
    await broadcast({"type": "scores", "scores": scores[:]})


async def broadcast_top() -> None:
    top = sorted(supporters.items(), key=lambda x: x[1], reverse=True)[:3]
    await broadcast({
        "type": "top_supporters",
        "list": [{"username": u, "coins": c} for u, c in top],
    })


def get_username(user) -> str:
    if user is None:
        return "user"
    return (
        getattr(user, "unique_id", None)
        or getattr(user, "uniqueId", None)
        or getattr(user, "nickname", None)
        or "user"
    )


def find_player_for_gift(gift_name: str, username: str) -> int:
    key = str(gift_name or "").lower().strip()
    if key in GIFT_MAP:
        return GIFT_MAP[key]
    for gift_key, player in GIFT_MAP.items():
        if gift_key in key or key in gift_key:
            return player
    return abs(hash(username)) % PLAYER_COUNT


async def validate_api_key(api_key: str) -> tuple[bool, str]:
    if not api_key or len(api_key.strip()) < 8:
        return False, "API key çox qısadır / boşdur"
    if not TIKTOK_AVAILABLE:
        return False, "TikTokLive yüklənməyib"
    try:
        WebDefaults.tiktok_sign_api_key = api_key.strip()
        return True, "API key qəbul olundu"
    except Exception as e:
        return False, f"Key xətası: {e}"


async def on_connect(event):
    room_id = getattr(event, "room_id", None)
    username = getattr(event, "unique_id", None) or current_user
    print(f"[TikTok] CONNECTED @{username} room={room_id}")
    await broadcast({
        "type": "status",
        "message": f"LIVE @{username}",
        "connected": True,
        "username": username,
        "room_id": room_id,
    })


async def on_disconnect(event):
    print("[TikTok] DISCONNECTED")
    await broadcast({"type": "status", "message": "TikTok disconnected", "connected": False})


async def on_gift(event):
    try:
        gift = getattr(event, "gift", None)
        if gift is None:
            return
        user = getattr(event, "user", None)
        username = get_username(user)
        gift_name = str(getattr(gift, "name", None) or "Unknown Gift").strip()
        coins = getattr(gift, "diamond_count", None) or getattr(gift, "diamondCount", None) or 1
        try:
            coins = int(coins)
        except Exception:
            coins = 1
        count = getattr(event, "repeat_count", None) or getattr(event, "repeatCount", None) or 1
        try:
            count = int(count)
        except Exception:
            count = 1
        count = max(1, count)

        gift_type = getattr(gift, "type", None)
        streaking = bool(getattr(event, "streaking", False))
        repeat_end = getattr(event, "repeat_end", None)
        try:
            repeat_end = int(repeat_end)
        except Exception:
            repeat_end = 1 if repeat_end else 0
        if gift_type == 1 and streaking and not repeat_end:
            return

        supporters[username] = supporters.get(username, 0) + coins * count
        player_id = find_player_for_gift(gift_name, username)
        points = GIFT_POINTS * count
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
        print("[Gift] ERROR:", type(exc).__name__, str(exc))


async def on_like(event):
    global total_likes, like_points_given
    try:
        amount = getattr(event, "count", None) or getattr(event, "total", None) or 1
        try:
            amount = int(amount)
        except Exception:
            amount = 1
        amount = max(1, amount)
        total_likes += amount
        room_total = getattr(event, "total", None) or total_likes
        user = getattr(event, "user", None)
        username = get_username(user)
        await broadcast({"type": "like", "amount": amount, "total": room_total, "username": username})
        should_have = total_likes // LIKE_EVERY
        while like_points_given < should_have:
            like_points_given += 1
            player_id = abs(hash(username)) % PLAYER_COUNT
            scores[player_id] += LIKE_POINTS
            await broadcast_scores()
    except Exception as exc:
        print("[Like] ERROR:", type(exc).__name__, str(exc))


async def on_follow(event):
    try:
        user = getattr(event, "user", None)
        username = get_username(user)
        player_id = abs(hash(username)) % PLAYER_COUNT
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
        print("[Follow] ERROR:", type(exc).__name__, str(exc))


async def start_tiktok(username: str, api_key: str):
    global tiktok_client, current_user, current_api_key

    if not TIKTOK_AVAILABLE:
        await broadcast({"type": "status", "message": "TikTokLive yüklənməyib", "connected": False})
        return

    api_key = (api_key or "").strip()
    if not api_key:
        await broadcast({"type": "status", "message": "API key yoxdur", "connected": False})
        return

    current_api_key = api_key
    WebDefaults.tiktok_sign_api_key = api_key

    if tiktok_client is not None:
        try:
            await tiktok_client.disconnect()
        except Exception:
            pass

    current_user = username.lstrip("@").strip()
    if not current_user:
        await broadcast({"type": "status", "message": "Test rejimi (TikTok yoxdur)", "connected": False})
        return

    client = TikTokLiveClient(unique_id=current_user)
    tiktok_client = client
    client.add_listener(ConnectEvent, on_connect)
    client.add_listener(DisconnectEvent, on_disconnect)
    client.add_listener(GiftEvent, on_gift)
    client.add_listener(LikeEvent, on_like)
    client.add_listener(FollowEvent, on_follow)

    print(f"[TikTok] Connecting to @{current_user} ...")
    await broadcast({"type": "status", "message": f"@{current_user} qoşulur...", "connected": False})

    try:
        await client.start()
    except Exception as e:
        print("[TikTok] Connect error:", e)
        await broadcast({"type": "status", "message": f"Bağlantı xətası: {e}", "connected": False})


async def websocket_handler(request):
    global current_api_key, scores, supporters, total_likes, like_points_given
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    print("[WS] Client connected")

    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except Exception:
                continue

            msg_type = data.get("type")

            if msg_type == "set_api_key":
                api_key = (data.get("api_key") or "").strip()
                ok, message = await validate_api_key(api_key)
                if ok:
                    current_api_key = api_key
                await ws.send_str(json.dumps({
                    "type": "api_key_result", "ok": ok, "message": message,
                }, ensure_ascii=False))

            elif msg_type in ("set_user", "connect"):
                username = (data.get("username") or "").strip()
                api_key = (data.get("api_key") or current_api_key or "").strip()
                if username and not api_key:
                    await ws.send_str(json.dumps({
                        "type": "status", "message": "Əvvəlcə API key yazın", "connected": False,
                    }, ensure_ascii=False))
                    continue
                asyncio.create_task(start_tiktok(username, api_key))

            elif msg_type == "reset":
                scores = [0] * PLAYER_COUNT
                supporters = {}
                total_likes = 0
                like_points_given = 0
                await broadcast_scores()
                await broadcast_top()
    finally:
        clients.discard(ws)
        print("[WS] Client disconnected")
    return ws


async def index_handler(request):
    return web.FileResponse(ROOT / "index.html")


async def main():
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/", ROOT)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    print(f"Server started → http://{HOST}:{PORT}")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiohttp
from aiohttp import web

# ============================================================
# PirateTok
# ============================================================

TIKTOK_AVAILABLE = False
TikTokLiveClient = None
EventType = None

try:
    from piratetok_live import TikTokLiveClient, EventType
    TIKTOK_AVAILABLE = True
    print("=" * 70)
    print("[PirateTok] IMPORT OK")
    print("=" * 70)
except Exception as exc:
    print("=" * 70)
    print("[PirateTok] IMPORT FAILED")
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

# ============================================================
# GIFT MAP
# ============================================================

GIFT_MAP = {
    "rose": 0, "gül": 0, "gul": 0, "my first rose": 0, "rosa": 0,
    "tiktok": 1,
    "flame heart": 2, "flameheart": 2, "flame": 2,
    "gg": 3,
    "ice cream cone": 4, "ice cream": 4, "icecream": 4, "dondurma": 4,
    "football": 5, "futbol": 5, "soccer": 5, "soccer ball": 5,
    "heart puff": 6, "heartpuff": 6,
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

# ============================================================
# BROADCAST
# ============================================================

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
    top = sorted(supporters.items(), key=lambda item: item[1], reverse=True)[:3]
    await broadcast({
        "type": "top_supporters",
        "list": [{"username": u, "coins": c} for u, c in top],
    })

# ============================================================
# HELPERS
# ============================================================

def get_username(user_data) -> str:
    if not user_data:
        return "user"
    if isinstance(user_data, dict):
        return (
            user_data.get("uniqueId")
            or user_data.get("unique_id")
            or user_data.get("nickname")
            or "user"
        )
    return "user"

def find_player_for_gift(gift_name: str, username: str) -> int:
    key = str(gift_name or "").lower().strip()
    player_id = GIFT_MAP.get(key)
    if player_id is not None:
        return player_id
    for gift_key, player in GIFT_MAP.items():
        if gift_key in key or key in gift_key:
            return player
    return abs(hash(username)) % PLAYER_COUNT

# ============================================================
# EVENT HANDLERS (PirateTok)
# ============================================================

async def handle_connect(evt):
    username = current_user
    print(f"[TikTok] CONNECTED @{username}")
    await broadcast({
        "type": "status",
        "message": f"LIVE @{username}",
        "connected": True,
        "username": username,
    })

async def handle_disconnect(evt):
    print("[TikTok] DISCONNECTED")
    await broadcast({
        "type": "status",
        "message": "TikTok disconnected",
        "connected": False,
    })

async def handle_gift(evt):
    try:
        data = getattr(evt, "data", {}) or {}
        user = data.get("user", {})
        gift = data.get("gift", {})

        username = get_username(user)
        gift_name = gift.get("name") or gift.get("giftName") or "Unknown Gift"
        gift_name = str(gift_name).strip()

        coins = gift.get("diamondCount") or gift.get("diamond_count") or 1
        try:
            coins = int(coins)
        except Exception:
            coins = 1

        count = data.get("repeatCount") or data.get("repeat_count") or 1
        try:
            count = int(count)
        except Exception:
            count = 1
        count = max(1, count)

        # Streak filter (sadə)
        repeat_end = data.get("repeatEnd") or data.get("repeat_end")
        if repeat_end is False or repeat_end == 0:
            # hələ streak davam edir, bəzən skip etmək olar
            pass

        print(f"[Gift] @{username} -> {gift_name} x{count} ({coins} diamonds)")

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

async def handle_like(evt):
    global total_likes, like_points_given
    try:
        data = getattr(evt, "data", {}) or {}
        amount = data.get("count") or data.get("likeCount") or 1
        try:
            amount = int(amount)
        except Exception:
            amount = 1
        amount = max(1, amount)

        total_likes += amount
        room_total = data.get("total") or total_likes

        user = data.get("user", {})
        username = get_username(user)

        await broadcast({
            "type": "like",
            "amount": amount,
            "total": room_total,
            "username": username,
        })

        should_have = total_likes // LIKE_EVERY
        while like_points_given < should_have:
            like_points_given += 1
            player_id = abs(hash(username)) % PLAYER_COUNT
            scores[player_id] += LIKE_POINTS
            await broadcast_scores()

    except Exception as exc:
        print("[Like] ERROR:", type(exc).__name__, str(exc))

async def handle_follow(evt):
    try:
        data = getattr(evt, "data", {}) or {}
        user = data.get("user", {})
        username = get_username(user)

        player_id = abs(hash(username)) % PLAYER_COUNT
        scores[player_id] += FOLLOW_POINTS

        print(f"[Follow] @{username}")

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

# ============================================================
# TIKTOK CONNECTION
# ============================================================

async def start_tiktok(username: str):
    global tiktok_client, tiktok_task, current_user

    if not TIKTOK_AVAILABLE:
        await broadcast({
            "type": "status",
            "message": "PirateTok yüklənməyib",
            "connected": False,
        })
        return

    # Köhnə bağlantını bağla
    if tiktok_client is not None:
        try:
            await tiktok_client.disconnect()
        except Exception:
            pass

    current_user = username.lstrip("@")
    client = TikTokLiveClient(current_user)
    tiktok_client = client

    # Event-ləri bağla
    @client.on(EventType.connected)
    async def _on_connected(evt):
        await handle_connect(evt)

    @client.on(EventType.disconnected)
    async def _on_disconnected(evt):
        await handle_disconnect(evt)

    @client.on(EventType.gift)
    async def _on_gift(evt):
        await handle_gift(evt)

    @client.on(EventType.like)
    async def _on_like(evt):
        await handle_like(evt)

    @client.on(EventType.follow)
    async def _on_follow(evt):
        await handle_follow(evt)

    print(f"[TikTok] Connecting to @{current_user} ...")

    try:
        await client.start()
    except Exception as e:
        print("[TikTok] Start error:", e)
        await broadcast({
            "type": "status",
            "message": f"Bağlantı xətası: {e}",
            "connected": False,
        })

# ============================================================
# WEBSOCKET + HTTP
# ============================================================

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    print("[WS] Client connected")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue

                if data.get("type") == "connect":
                    username = data.get("username", "").strip()
                    if username:
                        asyncio.create_task(start_tiktok(username))

                elif data.get("type") == "reset":
                    global scores, supporters, total_likes, like_points_given
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
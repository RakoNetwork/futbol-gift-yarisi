#!/usr/bin/env python3
"""
Football Gift Race — TikTok Live server
Termux / Android ready
"""

# TikTokLive importu başarısız olsa bile aşağıdaki fonksiyon imzalarındaki
# (event: ConnectEvent gibi) tip belirteçleri satır çalışma zamanında
# değerlendirilmesin diye — yoksa NameError ile tüm uygulama çöküyordu.
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from aiohttp import web
import aiohttp

try:
    import EulerApiSdk.api.tik_tok_live as _euler_ttl
    if not hasattr(_euler_ttl, "sign_webcast_url"):
        # Bu build ortamındaki EulerApiSdk sürümünde sign_webcast_url hiç yok.
        # TikTokLive'ın asıl imzalama kodu (TikTokSigner.webcast_sign) bunu
        # zaten kullanmıyor, kendi httpx isteğini atıyor — bu isim sadece
        # modül import edilirken var olsun diye lazım. Zararsız bir
        # placeholder koyup importun patlamasını engelliyoruz.
        class _SignWebcastUrlPlaceholder:
            pass
        _euler_ttl.sign_webcast_url = _SignWebcastUrlPlaceholder
        print("[DEBUG] sign_webcast_url placeholder ile dolduruldu")
except Exception as e:
    print("[DEBUG] EulerApiSdk.api.tik_tok_live import edilemedi:", type(e).__name__, e)

try:
    import EulerApiSdk
    print("[DEBUG] EulerApiSdk sürümü:", getattr(EulerApiSdk, "__version__", "bilinmiyor"))
    print("[DEBUG] EulerApiSdk konumu:", getattr(EulerApiSdk, "__file__", "?"))
except Exception as e:
    print("[DEBUG] EulerApiSdk hiç import edilemedi:", e)

try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import (
        ConnectEvent, DisconnectEvent, GiftEvent,
        LikeEvent, FollowEvent, ShareEvent, CommentEvent
    )
    TIKTOK_AVAILABLE = True
except Exception as _tiktok_import_error:
    TIKTOK_AVAILABLE = False
    # Bu sınıfları da None yapıyoruz; `from __future__ import annotations`
    # zaten fonksiyon imzalarındaki tip belirteçlerinin çalışma zamanında
    # değerlendirilmesini engelliyor, ama olası başka bir referansa karşı
    # (ör. izinsiz bir yerde ConnectEvent() çağrılırsa) yine de tanımlı olsunlar.
    TikTokLiveClient = None
    ConnectEvent = DisconnectEvent = GiftEvent = None
    LikeEvent = FollowEvent = ShareEvent = CommentEvent = None
    print(f"[TikTokLive import failed] {type(_tiktok_import_error).__name__}: {_tiktok_import_error}")

HOST = "0.0.0.0"
PORT = 8000
PLAYER_COUNT = 7

# Gift → player (exact mapping requested)
GIFT_MAP = {
    # 0 NƏRİMAN — Azerbaycan — Rose
    "rose": 0, "gül": 0, "gul": 0, "my first rose": 0, "rosa": 0,
    # 1 ARDA — Türkiye — TikTok
    "tiktok": 1,
    # 2 GOLOVIN — Rusya — Flame Heart
    "flame heart": 2, "flameheart": 2, "flame": 2,
    # 3 CHHETRI — Hindistan — GG
    "gg": 3,
    # 4 PULISIC — ABD — Ice Cream
    "ice cream cone": 4, "ice cream": 4, "icecream": 4, "dondurma": 4,
    # 5 MESSI — Arjantin — Football / Futbol
    "football": 5, "futbol": 5, "soccer": 5, "soccer ball": 5,
    # 6 RONALDO — Portekiz — Heart Puff
    "heart puff": 6, "heartpuff": 6, "heart puff": 6,
}

GIFT_POINTS = 1
FOLLOW_POINTS = 2
LIKE_POINTS = 1          # Her LIKE_EVERY like = +1 puan
LIKE_EVERY = 20          # Her 20 like'da 1 puan

# Ülke oyuncu indeksleri
AZERBAIJAN_PLAYER = 0    # 🇦🇿 NƏRİMAN
TURKEY_PLAYER = 1        # 🇹🇷 ARDA

clients = set()
total_likes = 0
like_points_given = 0    # Kaç tane like puanı verildi (20'lik dilimler)
supporters = {}
scores = [0] * PLAYER_COUNT
tiktok_client = None
tiktok_task = None
current_user = ""

ROOT = Path(__file__).parent.resolve()


async def broadcast(data: dict):
    if not clients:
        return
    msg = json.dumps(data, ensure_ascii=False)
    dead = []
    for ws in list(clients):
        try:
            await ws.send_str(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def broadcast_scores():
    await broadcast({"type": "scores", "scores": scores[:]})


async def broadcast_top():
    top = sorted(supporters.items(), key=lambda x: x[1], reverse=True)[:3]
    await broadcast({
        "type": "top_supporters",
        "list": [{"username": u, "coins": c} for u, c in top]
    })


# ---------- TikTok handlers ----------
async def on_connect(event: ConnectEvent):
    print(f"[TikTok] LIVE connected @{event.unique_id} room={tiktok_client.room_id}")
    await broadcast({
        "type": "status",
        "message": f"LIVE @{event.unique_id}",
        "connected": True,
        "username": event.unique_id
    })


async def on_disconnect(event: DisconnectEvent):
    print("[TikTok] Disconnected")
    await broadcast({"type": "status", "message": "TikTok disconnected", "connected": False})


_avatar_debug_done = False


def _extract_avatar(user) -> str | None:
    """TikTokLive user-dən profil şəkli URL."""
    global _avatar_debug_done
    if user is None:
        return None
    found = []

    def walk(obj, depth=0):
        if obj is None or depth > 5:
            return
        if isinstance(obj, str):
            if obj.startswith("http") and ("tiktok" in obj or "byteoversea" in obj or "avt" in obj or "avatar" in obj or "webp" in obj or "jpeg" in obj or "png" in obj):
                found.append(obj)
            return
        if isinstance(obj, (list, tuple)):
            for x in obj[:8]:
                walk(x, depth+1)
            return
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v, depth+1)
            return
        # object
        for meth in ("model_dump", "dict", "as_dict", "to_dict"):
            fn = getattr(obj, meth, None)
            if callable(fn):
                try:
                    walk(fn(), depth+1)
                    return
                except Exception:
                    pass
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            for v in d.values():
                walk(v, depth+1)
        for a in ("url_list", "urlList", "urls", "url", "uri", "avatar_thumb", "avatar_medium", "avatar", "profile_picture"):
            try:
                walk(getattr(obj, a, None), depth+1)
            except Exception:
                pass

    walk(user)

    # unique_id ilə fallback CDN (bəzən işləyir)
    if not found:
        uid = getattr(user, "unique_id", None) or getattr(user, "uniqueId", None)
        # skip unreliable CDN guess

    for u in found:
        if isinstance(u, str) and u.startswith("http"):
            return u

    if not _avatar_debug_done:
        _avatar_debug_done = True
        try:
            print("[Avatar debug] attrs:", [a for a in dir(user) if "avatar" in a.lower() or "profile" in a.lower() or "pic" in a.lower()])
            print("[Avatar debug] found urls:", found[:3])
        except Exception as e:
            print("[Avatar debug]", e)
    return None



async def on_gift(event: GiftEvent):
    try:
        gift = event.gift
        if gift is None:
            return

        username = "user"
        avatar = None
        if event.user is not None:
            username = (getattr(event.user, "nickname", None)
                        or getattr(event.user, "unique_id", None)
                        or "user")
            avatar = _extract_avatar(event.user)

        gift_name = (getattr(gift, "name", None) or "?").strip()
        coins = (getattr(gift, "diamond_count", None)
                 or getattr(gift, "diamondCount", None)
                 or 1) or 1
        count = getattr(event, "repeat_count", None) or getattr(event, "repeatCount", None) or 1
        try:
            count = int(count)
        except Exception:
            count = 1

        # Streak: yalnız bitmiş streak və ya qeyri-streak gift xal versin
        gift_type = getattr(gift, "type", None)
        streakable = bool(getattr(gift, "streakable", False) or gift_type == 1)
        streaking = bool(getattr(event, "streaking", False))
        repeat_end = getattr(event, "repeat_end", None)
        if repeat_end is None:
            repeat_end = getattr(event, "repeatEnd", None)
        try:
            repeat_end = int(repeat_end) if repeat_end is not None else 0
        except Exception:
            repeat_end = 1 if repeat_end else 0

        # davam edən streak (son deyil) — yalnız log
        is_mid_streak = streakable and streaking and not repeat_end

        streak_tag = " [streak]" if is_mid_streak else (" [end]" if (streakable and not streaking) else "")
        print(f"[Gift] {username} → {gift_name} x{count}{streak_tag} ({coins}💎)")

        if is_mid_streak:
            return

        supporters[username] = supporters.get(username, 0) + coins * count

        key = gift_name.lower().strip()
        player_id = GIFT_MAP.get(key)
        if player_id is None:
            for k, pid in GIFT_MAP.items():
                if k in key or key in k:
                    player_id = pid
                    break
        if player_id is None:
            player_id = abs(hash(username)) % PLAYER_COUNT

        points = GIFT_POINTS * max(1, count)
        scores[player_id] += points

        print(f"       → P{player_id} (+{points}) score={scores[player_id]} AD={username}"
              + (f" AVATAR=ok" if avatar else " AVATAR=yox")
              + f" gift={gift_name!r}")
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
        await broadcast(payload)
        await broadcast_top()
    except Exception as e:
        print("Gift error:", e)


async def on_like(event: LikeEvent):
    """Her 20 like → Azerbaycan'a (Player 0) +1 puan + isim/avatar göster"""
    global total_likes, like_points_given
    try:
        # Yeni TikTokLive: event.count / event.total
        amount = getattr(event, "count", None)
        if amount is None:
            amount = getattr(event, "total", None)
        try:
            amount = int(amount) if amount is not None else 1
        except Exception:
            amount = 1
        if amount < 1:
            amount = 1

        total_likes += amount

        room_total = getattr(event, "total", None)
        try:
            room_total = int(room_total) if room_total is not None else total_likes
        except Exception:
            room_total = total_likes

        # Like atan kişinin isim + avatar
        username = "user"
        avatar = None
        if getattr(event, "user", None) is not None:
            username = (getattr(event.user, "nickname", None)
                        or getattr(event.user, "unique_id", None)
                        or "user")
            avatar = _extract_avatar(event.user)

        # Frontend'e like bilgisi gönder
        await broadcast({
            "type": "like",
            "amount": amount,
            "total": room_total,
            "username": username
        })

        # Her 20 like'da Azerbaycan'a 1 puan ver + isim/avatar göster
        should_have = total_likes // LIKE_EVERY
        new_points = should_have - like_points_given
        if new_points > 0:
            like_points_given = should_have
            scores[AZERBAIJAN_PLAYER] += new_points * LIKE_POINTS
            print(f"[Like] {username} → {total_likes} like → Azerbaycan +{new_points} puan (toplam: {scores[AZERBAIJAN_PLAYER]})")
            await broadcast({
                "type": "gift",
                "username": username,
                "player_name": username,
                "gift_name": "Like",
                "gift_key": "like",
                "coins": 0,
                "count": new_points,
                "player_id": AZERBAIJAN_PLAYER,
                "points": new_points * LIKE_POINTS,
                "scores": scores[:],
                "avatar": avatar or "",
                "sound": True,
                "reason": "like"
            })
            await broadcast_top()
    except Exception:
        # Heç bir xəta konsola yazılmasın
        pass



async def on_follow(event: FollowEvent):
    """Her follow → Türkiye'ye (Player 1 / ARDA) +2 puan + isim/avatar göster"""
    try:
        username = "user"
        avatar = None
        if getattr(event, "user", None) is not None:
            username = (getattr(event.user, "nickname", None)
                        or getattr(event.user, "unique_id", None)
                        or "user")
            avatar = _extract_avatar(event.user)

        pid = TURKEY_PLAYER  # Her zaman Türkiye (ARDA)
        scores[pid] += FOLLOW_POINTS
        print(f"[Follow] @{username} → Türkiye +{FOLLOW_POINTS} puan (toplam: {scores[pid]})")

        await broadcast({"type": "follow", "username": username})
        # Gift gibi gönder ki isim + avatar oyuncuda görünsün
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
            "avatar": avatar or "",
            "sound": True,
            "reason": "follow"
        })
        await broadcast_top()
    except Exception as e:
        print("Follow error:", e)


async def on_share(event: ShareEvent):
    try:
        username = event.user.nickname or event.user.unique_id or "user"
        await broadcast({"type": "share", "username": username})
    except Exception as e:
        print("Share error:", e)


async def on_comment(event: CommentEvent):
    try:
        await broadcast({
            "type": "comment",
            "username": event.user.nickname or event.user.unique_id or "user",
            "comment": event.comment or ""
        })
    except Exception as e:
        print("Comment error:", e)


async def stop_tiktok():
    global tiktok_client, tiktok_task
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
    """Check is_live first, then connect with detailed errors."""
    global tiktok_client, tiktok_task, current_user

    if not TIKTOK_AVAILABLE:
        await broadcast({
            "type": "status",
            "message": "TikTokLive quraşdırılmayıb: pip install TikTokLive",
            "connected": False
        })
        return

    username = (username or "").strip().lstrip("@")
    if not username:
        await broadcast({"type": "status", "message": "Username boşdur", "connected": False})
        return

    await stop_tiktok()
    current_user = username
    await broadcast({
        "type": "status",
        "message": f"Yoxlanılır @{username} ...",
        "connected": False
    })
    print(f"[TikTok] Checking is_live @{username} ...")

    client = TikTokLiveClient(unique_id=f"@{username}")

    try:
        is_live = await client.is_live()
    except Exception as e:
        err = str(e)
        print(f"[TikTok] is_live error: {err}")
        await broadcast({
            "type": "status",
            "message": f"Yoxlama xətası: {err[:120]}",
            "connected": False,
            "error": err
        })
        return

    if not is_live:
        print(f"[TikTok] @{username} is NOT live")
        await broadcast({
            "type": "status",
            "message": f"@{username} hazırda LIVE deyil",
            "connected": False
        })
        return

    print(f"[TikTok] @{username} IS LIVE — connecting ...")
    await broadcast({
        "type": "status",
        "message": f"LIVE tapıldı, qoşulur @{username} ...",
        "connected": False
    })

    client.add_listener(ConnectEvent, on_connect)
    client.add_listener(DisconnectEvent, on_disconnect)
    client.add_listener(GiftEvent, on_gift)
    client.add_listener(LikeEvent, on_like)
    client.add_listener(FollowEvent, on_follow)
    client.add_listener(ShareEvent, on_share)
    client.add_listener(CommentEvent, on_comment)

    tiktok_client = client
    try:
        # Non-blocking start; returns Task
        task = await client.start(fetch_live_check=False, fetch_gift_info=True)
        tiktok_task = task
        print(f"[TikTok] start() OK @{username}")
    except Exception as e:
        err = str(e)
        print(f"[TikTok] start/connect failed: {err}")
        tiktok_client = None
        await broadcast({
            "type": "status",
            "message": f"Qoşulma xətası: {err[:140]}",
            "connected": False,
            "error": err
        })


# ---------- HTTP / WS ----------
async def ws_handler(request):
    global total_likes, like_points_given
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    clients.add(ws)
    print("WS client +1 =", len(clients))

    await ws.send_str(json.dumps({
        "type": "init",
        "scores": scores[:],
        "total_likes": total_likes,
        "supporters": [{"username": u, "coins": c}
                       for u, c in sorted(supporters.items(), key=lambda x: -x[1])[:3]],
        "gift_map": {k: v for k, v in GIFT_MAP.items()},
        "connected": tiktok_client is not None,
        "username": current_user
    }))

    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except Exception:
                continue
            t = data.get("type")

            if t == "set_user":
                username = (data.get("username") or "").strip().lstrip("@")
                if username:
                    asyncio.create_task(start_tiktok(username))
                else:
                    await stop_tiktok()
                    await broadcast({"type": "status", "message": "Test rejimi", "connected": False})

            elif t == "gift":
                # test gift from UI
                pid = int(data.get("player_id", 0)) % PLAYER_COUNT
                points = int(data.get("points", GIFT_POINTS))
                username = data.get("username", "test")
                gift_name = data.get("gift_name", "Test")
                coins = int(data.get("coins", 1))
                supporters[username] = supporters.get(username, 0) + coins
                scores[pid] += points
                await broadcast({
                    "type": "gift",
                    "username": username,
                    "gift_name": gift_name,
                    "player_id": pid,
                    "points": points,
                    "coins": coins,
                    "scores": scores[:],
                    "player_name": username,
                    "sound": True
                })
                await broadcast_top()

            elif t == "reset_scores":
                for i in range(PLAYER_COUNT):
                    scores[i] = 0
                total_likes = 0
                like_points_given = 0
                await broadcast_scores()

    finally:
        clients.discard(ws)
        print("WS client -1 =", len(clients))
    return ws


async def index(request):
    for name in ("football_gift_race_fixed.html", "index.html"):
        p = ROOT / name
        if p.is_file():
            resp = web.FileResponse(p)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp
    return web.Response(text="football_gift_race_fixed.html not found", status=404)


def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/football_gift_race_fixed.html", index)
    if (ROOT / "assets").is_dir():
        app.router.add_static("/assets/", ROOT / "assets")
    return app


async def main():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    print("=" * 50)
    print(" Football Gift Race + TikTok Live")
    print(f" http://localhost:{PORT}")
    print("=" * 50)
    if not TIKTOK_AVAILABLE:
        print(" WARNING: TikTokLive not installed")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
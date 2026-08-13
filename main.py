#!/usr/bin/env python3
"""
Futbol Gift Yarışı — Android giriş noktası (p4a webview bootstrap)

Buildozer'ın "webview" bootstrap'i bu dosyayı çalıştırır, arka planda
aiohttp sunucusu (server.py) ayağa kalkar ve native Android WebView
otomatik olarak http://127.0.0.1:8000 adresini açar.

Masaüstünde/Termux'ta test etmek için de doğrudan çalıştırılabilir:
    python main.py
"""

import asyncio

from server import main as server_main

if __name__ == "__main__":
    try:
        asyncio.run(server_main())
    except KeyboardInterrupt:
        print("Durduruldu.")

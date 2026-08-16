[app]

title = Futbol Gift Yarışı
package.name = futbolgiftyarisi
package.domain = org.revan.futbolgift
source.dir = .
source.include_exts = py,html,js,css,json,png,jpg,jpeg,gif,ttf,otf,ico,webp
version = 1.0.0

# ============================================================
# PYTHON
# ============================================================

requirements = python3==3.11.9,hostpython3==3.11.9,aiohttp,httpx,httpcore,h11,anyio,sniffio,certifi,idna,charset-normalizer,attrs,aiosignal,multidict,yarl,frozenlist,async-timeout,pyjnius,requests,websocket-client,piratetok-live-py

# ============================================================
# WEBVIEW
# ============================================================

p4a.bootstrap = webview
p4a.port = 8000

# ============================================================
# ANDROID
# ============================================================

orientation = portrait
fullscreen = 1
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True

# ============================================================
# COMPILER
# ============================================================

android.additional_cflags = -D_POSIX_C_SOURCE=200809L

[buildozer]
log_level = 2
warn_on_root = 1
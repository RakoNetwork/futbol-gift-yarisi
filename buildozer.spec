[app]

title = Futbol Gift Yarışı

package.name = futbolgiftyarisi

package.domain = org.revan.futbolgift

source.dir = .

source.include_exts = py,html,js,css,json,png,jpg,jpeg,gif,ttf,otf,ico,webp

version = 1.0.0


# ============================================================
# PYTHON DEPENDENCIES
# ============================================================

requirements = python3,aiohttp,httpx,httpcore,h11,anyio,sniffio,certifi,idna,charset-normalizer,attrs,aiosignal,multidict,yarl,frozenlist,async-timeout,pyee==13.0.1,ffmpy,websockets,websockets_proxy==0.1.3,betterproto==2.0.0b7,mashumaro,protobuf,protobuf3-to-dict,typing-extensions,EulerApiSdk==0.0.3,TikTokLive==6.6.5,pyjnius


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

# ÖNEMLİ:
# remote_debugging.o / preadv / pwritev problemi üçün 24
android.minapi = 24

android.ndk = 25b

android.archs = arm64-v8a

android.allow_backup = True

android.accept_sdk_license = True


# ============================================================
# COMPILER FIX
# ============================================================

android.additional_cflags = -D_POSIX_C_SOURCE=200809L


# ============================================================
# BUILD
# ============================================================

[buildozer]

log_level = 2

warn_on_root = 1
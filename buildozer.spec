[app]

title = Futbol Gift Yarışı
package.name = futbolgiftyarisi
package.domain = org.revan.futbolgift

source.dir = .
source.include_exts = py,html,js,css,json,png,jpg,jpeg,gif,ttf,otf,ico

version = 1.0.0

# ============================================================
# PYTHON / TIKTOKLIVE
# ============================================================

requirements = python3==3.11.9,hostpython3==3.11.9,aiohttp,aiosignal,attrs,multidict,yarl,frozenlist,async-timeout,charset-normalizer,idna,certifi,protobuf,pyee,requests,websocket-client,betterproto,betterproto2==0.9.0,TikTokLive==6.6.5,TikTokLiveProto,EulerApiSdk==0.1.1,httpx,httpcore,h11,anyio,sniffio,protobuf3-to-dict,websockets,ffmpy,mashumaro,typing-extensions,pyjnius,pydantic==2.12.2,pydantic-core==2.41.4,annotated-types,typing-inspection,python-socks,websockets-proxy

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

# icon.filename = %(source.dir)s/icon.png

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK
android.api = 33
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True

# ============================================================
# BUILD
# ============================================================

[buildozer]

log_level = 2
warn_on_root = 1
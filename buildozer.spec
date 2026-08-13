[app]

title = Futbol Gift Yarışı
package.name = futbolgiftyarisi
package.domain = org.revan.futbolgift

source.dir = .
source.include_exts = py,html,js,css,json,png,jpg,jpeg,gif,ttf,otf,ico

version = 1.0.0

# TikTokLive + aiohttp bağımlılıkları. Sürümleri gerekirse pin'leyin.
requirements = python3==3.11.9,hostpython3==3.11.9,aiohttp,aiosignal,attrs,multidict,yarl,frozenlist,async-timeout,charset-normalizer,idna,certifi,protobuf,pyee,requests,websocket-client,betterproto,betterproto2,TikTokLive,TikTokLiveProto,httpx,httpcore,h11,anyio,sniffio,protobuf3-to-dict,websockets,ffmpy,mashumaro,typing-extensions,pyjnius

# Bu satır, p4a'ya native WebView ile HTML/JS arayüzü göstermesini söyler.
# main.py arka planda sunucuyu ayağa kaldırır, WebView otomatik olarak
# p4a.port değerindeki adrese bağlanır.
p4a.bootstrap = webview
p4a.port = 8000

orientation = portrait
fullscreen = 1

# icon.png'yi repoya ekleyip aşağıdaki satırı açabilirsiniz
# icon.filename = %(source.dir)s/icon.png

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK
android.api = 33
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
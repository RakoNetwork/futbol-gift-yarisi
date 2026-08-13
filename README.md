# Futbol Gift Yarışı

TikTok Live hediyeleriyle oynanan 7 oyunculu futbol yarış oyunu. Python
(aiohttp) backend + tek dosyalık HTML/CSS/JS frontend, WebSocket üzerinden
haberleşir. Standalone Android APK için Buildozer "webview" bootstrap
kullanır (Termux gerekmez).

## Dosya yapısı

```
.
├── main.py              # Android giriş noktası (webview bootstrap bunu çalıştırır)
├── server.py             # aiohttp + TikTokLive backend, WebSocket + statik dosya sunar
├── index.html             # Tek dosyalık frontend (oyun arayüzü)
├── buildozer.spec         # Android APK build ayarları
├── requirements-desktop.txt
└── .github/workflows/build-apk.yml   # GitHub Actions ile otomatik APK build
```

## Masaüstü / Termux'ta test

```bash
pip install -r requirements-desktop.txt
python main.py
# tarayıcıda http://localhost:8000 adresini aç
```

## Android APK — GitHub Actions ile (önerilen, JAVA_HOME derdi yok)

Yerelde Buildozer kurmaya uğraşmak yerine build işini GitHub'a yaptırın:

1. Bu repoyu GitHub'a push edin (aşağıya bakın).
2. GitHub'da repo sayfasında **Actions** sekmesine gidin.
3. "Build APK" workflow'unu görün, `main` branch'e her push'ta otomatik
   çalışır. İsterseniz **Run workflow** ile elle de tetikleyebilirsiniz.
4. Build bitince (~10-20 dk) **Artifacts** bölümünden
   `futbolgiftyarisi-apk` dosyasını indirin — telefonunuza kurabileceğiniz
   `.apk` bu.

Bu yöntem sizin makinenizde Android SDK/NDK/JAVA_HOME kurmanıza gerek
bırakmaz; hepsi GitHub'ın sunucusunda hazır gelir.

## Android APK — Yerelde Buildozer ile (alternatif)

```bash
pip install buildozer cython
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64   # sisteminize göre değişir
buildozer android debug
```

APK, `bin/` klasöründe oluşur.

## GitHub'a push etme

```bash
git init
git add .
git commit -m "İlk sürüm: Futbol Gift Yarışı"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADIN/futbol-gift-yarisi.git
git push -u origin main
```

`KULLANICI_ADIN` ve repo adını GitHub'da oluşturduğunuz repoya göre
değiştirin. Repoyu GitHub üzerinden (github.com → New repository) önce
oluşturmanız gerekiyor.

## Notlar / bilinen riskler

- Workflow, `ArtemSBulgakov/buildozer-action@v1` yerine buildozer'ı
  doğrudan `ubuntu-22.04` runner'ı üzerinde çalıştırır. Bu action'ın
  kendi Docker imajı zaman zaman Ubuntu'nun deneysel/yayınlanmamış bir
  sürümüne güncellenip `openjdk-r` PPA'sının 404 vermesine yol açtığı
  için kaldırıldı.
- `TikTokLive` paketinin Android üzerinde (p4a) derlenmesi bazı
  bağımlılıklar (protobuf, websocket vb.) yüzünden sorun çıkarabilir.
  İlk build başarısız olursa Actions loglarındaki hata mesajına göre
  `buildozer.spec` içindeki `requirements` satırını güncelleyin.
- `buildozer.spec` içinde `icon.filename` satırı kapalı; kendi
  `icon.png` dosyanızı ekleyip satırı açabilirsiniz.
- `server.py` içindeki `GIFT_MAP` altı ülke/hediye eşlemesini içerir,
  `PLAYER_COUNT = 7` olduğu için eşleşmeyen hediyeler kullanıcı adının
  hash'ine göre rastgele bir oyuncuya düşer — istersen bunu 6'ya
  sabitleyip yedek oyuncuyu kaldırabilirsin.

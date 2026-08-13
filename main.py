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


def _hide_android_navigation():
    """Android'de durum çubuğunu ve navigasyon çubuğunu gizleyip
    tam ekran (immersive sticky) moduna geçer. Masaüstünde/Termux'ta
    pyjnius/android modülleri bulunamayacağı için sessizce atlanır."""
    try:
        from jnius import autoclass

        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        View = autoclass('android.view.View')
        activity = PythonActivity.mActivity

        flags = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        )

        def apply_flags(*_args):
            decor_view = activity.getWindow().getDecorView()
            decor_view.setSystemUiVisibility(flags)

        activity.runOnUiThread(apply_flags)

        # Kullanıcı ekrana dokununca sistem çubukları geçici olarak
        # tekrar belirebiliyor; odak her geri geldiğinde bayrakları
        # yeniden uygulayarak "sticky immersive" davranışını koruyoruz.
        try:
            from jnius import PythonJavaClass, java_method

            class _FocusListener(PythonJavaClass):
                __javainterfaces__ = ['android/view/ViewTreeObserver$OnWindowFocusChangeListener']
                __javacontext__ = 'app'

                @java_method('(Z)V')
                def onWindowFocusChanged(self, has_focus):
                    if has_focus:
                        activity.runOnUiThread(apply_flags)

            decor_view = activity.getWindow().getDecorView()
            listener = _FocusListener()
            decor_view.getViewTreeObserver().addOnWindowFocusChangeListener(listener)
            _hide_android_navigation._listener = listener  # referansı canlı tut
        except Exception as e:
            print(f"[Fullscreen] focus listener kurulamadı: {e}")

    except Exception as e:
        print(f"[Fullscreen] atlandı (muhtemelen Android değil): {e}")


if __name__ == "__main__":
    _hide_android_navigation()
    try:
        asyncio.run(server_main())
    except KeyboardInterrupt:
        print("Durduruldu.")
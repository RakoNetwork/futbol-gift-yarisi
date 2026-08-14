#!/usr/bin/env python3
"""
Futbol Gift Yarışı — Android giriş noktası

Buildozer/p4a webview bootstrap:
    main.py
        ↓
    server.py
        ↓
    aiohttp :8000
        ↓
    Android WebView
"""

import asyncio

from server import main as server_main


def _hide_android_navigation():
    """
    Android'de durum ve navigasyon çubuklarını gizler.

    Termux / masaüstünde pyjnius yoksa sessizce devam eder.
    """

    try:

        from jnius import (
            autoclass,
            PythonJavaClass,
            java_method
        )

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )

        View = autoclass(
            "android.view.View"
        )

        activity = (
            PythonActivity.mActivity
        )

        flags = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            |
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            |
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            |
            View.SYSTEM_UI_FLAG_FULLSCREEN
            |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        )

        def apply_flags(*_args):

            try:

                decor_view = (
                    activity
                    .getWindow()
                    .getDecorView()
                )

                decor_view.setSystemUiVisibility(
                    flags
                )

            except Exception as e:

                print(
                    "[Fullscreen] apply error:",
                    e
                )

        activity.runOnUiThread(
            apply_flags
        )

        # Android ekran odağı geri geldiğinde
        # immersive flags tekrar uygulanır.

        try:

            class FocusListener(
                PythonJavaClass
            ):

                __javainterfaces__ = [
                    "android/view/ViewTreeObserver$OnWindowFocusChangeListener"
                ]

                __javacontext__ = "app"

                @java_method("(Z)V")
                def onWindowFocusChanged(
                    self,
                    has_focus
                ):

                    if has_focus:

                        try:

                            activity.runOnUiThread(
                                apply_flags
                            )

                        except Exception:
                            pass

            decor_view = (
                activity
                .getWindow()
                .getDecorView()
            )

            listener = FocusListener()

            decor_view \
                .getViewTreeObserver() \
                .addOnWindowFocusChangeListener(
                    listener
                )

            # Listener GC tarafından silinmesin.
            _hide_android_navigation.listener = (
                listener
            )

        except Exception as e:

            print(
                "[Fullscreen] "
                "focus listener error:",
                e
            )

    except Exception as e:

        print(
            "[Fullscreen] skipped:",
            e
        )


async def run_server():

    await server_main()


def main():

    _hide_android_navigation()

    try:

        asyncio.run(
            run_server()
        )

    except KeyboardInterrupt:

        print(
            "Durduruldu."
        )


if __name__ == "__main__":

    main()
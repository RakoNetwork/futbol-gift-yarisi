#!/usr/bin/env python3

import asyncio

from server import main as server_main


def _hide_android_navigation():

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

                decor = (
                    activity
                    .getWindow()
                    .getDecorView()
                )

                decor.setSystemUiVisibility(
                    flags
                )

            except Exception as e:

                print(
                    "[Fullscreen] error:",
                    e
                )

        activity.runOnUiThread(
            apply_flags
        )

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

            decor = (
                activity
                .getWindow()
                .getDecorView()
            )

            listener = FocusListener()

            decor.getViewTreeObserver().addOnWindowFocusChangeListener(
                listener
            )

            _hide_android_navigation.listener = (
                listener
            )

        except Exception as e:

            print(
                "[Fullscreen] listener error:",
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
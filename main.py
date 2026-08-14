#!/usr/bin/env python3

from __future__ import annotations

import asyncio

from server import main as server_main


def hide_android_navigation():

    try:

        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )

        View = autoclass(
            "android.view.View"
        )

        activity = PythonActivity.mActivity

        flags = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        )

        decor = (
            activity
            .getWindow()
            .getDecorView()
        )

        decor.setSystemUiVisibility(flags)

        print("[Fullscreen] OK")

    except Exception as exc:

        print(
            "[Fullscreen] skipped:",
            type(exc).__name__,
            str(exc),
        )


async def run():

    await server_main()


def main():

    hide_android_navigation()

    try:

        asyncio.run(run())

    except KeyboardInterrupt:

        print("Durduruldu.")


if __name__ == "__main__":
    main()
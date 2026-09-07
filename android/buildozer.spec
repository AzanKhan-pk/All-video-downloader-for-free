[app]
# VidLoom Android
title = VidLoom
package.name = vidloom
package.domain = com.vidloom
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt
version = 1.0.0
requirements = python3,kivy,yt-dlp
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 35
android.minapi = 23
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1

[app:android]
android.add_src =
android.add_aars =
android.add_jars =
android.entrypoint = org.kivy.android.PythonActivity

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile build, same shape as Vivo RF Check's main.spec."""

import os
import sys

sys.path.insert(0, os.path.abspath("code"))
os.environ["DJANGO_SETTINGS_MODULE"] = "claro_rf_check.settings.desktop"
os.environ.setdefault("SECRET_KEY", "claro-rf-check-desktop-build")

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

tag = os.environ.get("CI_COMMIT_TAG", "dev")

apps = [
    "claro_rf_check",
    "combined",
    "ep_import",
    "home",
    "poscheck",
    "precheck",
    "reports",
    "theme",
    "users",
]

datas = [("code/static", "static")]
# Celery and these Django apps are imported by name, so PyInstaller does not
# see them. The desktop window has no Core Connect SSO login.
hiddenimports = [
    "waitress",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    *collect_submodules("whitenoise"),
    *collect_submodules("celery"),
    *collect_submodules("kombu"),
]
for package in ("rest_framework", "django_celery_beat", "django_htmx", "tailwind"):
    hiddenimports += collect_submodules(package)
    datas += collect_data_files(package)
# django-tailwind has no templatetags/__init__.py, so collect_submodules skips it.
hiddenimports.append("tailwind.templatetags.tailwind_tags")
skip_modules = {
    "users.authentication",
    "users.backends",
    "users.middleware",
    "users.sso",
    "users.urls",
    "users.views",
}
for app in apps:
    datas += collect_data_files(app)
    root = Path("code") / app
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        if path.name == "__init__.py":
            module = path.parent.relative_to(Path("code"))
        else:
            module = path.relative_to(Path("code")).with_suffix("")
        module_name = ".".join(module.parts)
        if module_name in skip_modules or module_name.startswith("users.tests"):
            continue
        hiddenimports.append(module_name)

a = Analysis(
    ["main.py"],
    pathex=["code"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["core_connect_sso"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"ClaroRFCheck-{tag}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)

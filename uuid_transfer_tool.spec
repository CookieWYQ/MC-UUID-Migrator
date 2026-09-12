# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec：打包 uuid_transfer_tool.py 为单文件 GUI 程序
# 用法：
#   pip install pyinstaller
#   pyinstaller uuid_transfer_tool.spec
# 产物：dist/UUID玩家数据迁移.exe

a = Analysis(
    ['uuid_transfer_tool.py'],
    pathex=[],
    binaries=[],
    datas=[('使用教程/*.md', '使用教程')],   # 教程 md 一并打进 exe（界面“使用教程”按钮查看）
    hiddenimports=['paramiko'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UUID玩家数据迁移',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                 # GUI 程序，不弹出控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='uuid_transfer_icon.ico',
)

@echo off
REM ============================================================
REM  一键构建单文件 exe（需要 Python 3.10+ 与 PyInstaller）
REM  产物：dist\UUID玩家数据迁移.exe
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 安装依赖...
python -m pip install --upgrade pyinstaller paramiko
if errorlevel 1 goto fail

echo [2/3] 清理旧的构建目录...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] 打包（单文件）...
pyinstaller uuid_transfer_tool.spec --noconfirm
if errorlevel 1 goto fail

echo.
echo 构建完成：dist\UUID玩家数据迁移.exe
pause
exit /b 0

:fail
echo.
echo 构建失败，请检查上面的错误信息。
pause
exit /b 1

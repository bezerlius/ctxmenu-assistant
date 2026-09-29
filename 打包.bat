@echo off
chcp 65001 >nul
setlocal

set PY=C:\Users\Berzelius\.workbuddy\binaries\python\versions\3.14.3\python.exe

echo ============================================
echo   一键自定义右键菜单助手 - 打包脚本
echo ============================================
echo.

cd /d "%~dp0"

echo [1/4] 生成图标...
"%PY%" make_icon.py
if errorlevel 1 goto err

echo.
echo [2/4] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ctxmenu.spec del /q ctxmenu.spec

echo.
echo [3/4] 打包中（首次约需 1-3 分钟）...
"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "右键菜单助手" ^
  --icon app.ico ^
  --add-data "app.ico;." ^
  --exclude-module numpy ^
  --exclude-module scipy ^
  --exclude-module openpyxl ^
  --exclude-module PIL ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  ctxmenu_gui.py
if errorlevel 1 goto err

echo.
echo [4/4] 完成！
echo.
echo 成品位置：%~dp0dist\右键菜单助手.exe
dir /b "dist\*.exe"
echo.
echo 双击即可运行，无需安装 Python。
pause
exit /b 0

:err
echo.
echo *** 打包失败，请查看上方错误信息 ***
pause
exit /b 1

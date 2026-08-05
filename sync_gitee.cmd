@echo off
rem 一键同步 GitHub + Gitee（本地代码推送到两个远端）
chcp 65001 >nul
cd /d C:\Users\enthalpy\WorkBuddy\Claw\notiforward

echo [1/2] 推送 GitHub (origin) ...
git push origin master
if errorlevel 1 (
    echo GitHub 推送失败，请检查网络/凭据
    pause
    exit /b 1
)

echo [2/2] 推送 Gitee ...
git push gitee master
if errorlevel 1 (
    echo Gitee 推送失败，请检查网络/凭据
    pause
    exit /b 1
)

echo.
echo 双端同步完成 ✔
pause

# NotiForward 一键构建脚本（微信版）
# 用法: powershell -ExecutionPolicy Bypass -File build_apk.ps1
# 说明: 每次构建前自动清理 gradle 状态（Windows 文件锁问题），输出微信版 APK 到 Claw 目录
$ErrorActionPreference = 'Continue'
$proj = 'C:\Users\enthalpy\WorkBuddy\Claw\notiforward'
$gradleHome = 'C:\Users\enthalpy\WorkBuddy\Claw\notiforward\.gradle-home4'
$gradle = 'C:\Users\enthalpy\.gradle\wrapper\dists\gradle-9.4.1-bin\arn2x92ynaizyzdaamcbpbhtj\gradle-9.4.1\bin\gradle.bat'
$apkOut = 'C:\Users\enthalpy\WorkBuddy\Claw\NotiForward.apk'

Write-Host '[1/2] 清理 gradle 状态...'
foreach ($t in @("$gradleHome\native", "$gradleHome\daemon", "$gradleHome\caches\9.4.1", "$gradleHome\caches\journal-1", "$proj\.gradle", "$proj\build", "$proj\app\build")) {
    if (Test-Path -LiteralPath $t) { Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction SilentlyContinue }
}
foreach ($lk in @("$gradleHome\caches\modules-2\modules-2.lock", "$env:USERPROFILE\.android\debug.keystore.lock")) {
    if (Test-Path -LiteralPath $lk) { Remove-Item -LiteralPath $lk -Force -ErrorAction SilentlyContinue }
}

Write-Host '[2/2] 构建 APK...'
$env:GRADLE_USER_HOME = $gradleHome
Set-Location $proj
& $gradle assembleDebug --no-daemon
if ($LASTEXITCODE -eq 0) {
    Copy-Item -Path "$proj\app\build\outputs\apk\debug\app-debug.apk" -Destination $apkOut -Force
    Write-Host "构建成功! APK: $apkOut"
} else {
    Write-Host "构建失败 (exit=$LASTEXITCODE)"
}

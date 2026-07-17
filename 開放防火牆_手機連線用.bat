@echo off
chcp 65001 >nul
echo 正在開放防火牆連接埠 8899（工資記錄計算程式 手機連線用）...
netsh advfirewall firewall show rule name="WageApp 8899" >nul 2>&1
if %errorlevel%==0 (
    echo 防火牆規則已存在，不需重複新增。
    goto end
)
netsh advfirewall firewall add rule name="WageApp 8899" dir=in action=allow protocol=TCP localport=8899
if %errorlevel%==0 (
    echo 完成！手機現在可以連線了。
) else (
    echo 失敗：請按右鍵用「以系統管理員身分執行」開啟本檔案。
)
:end
pause

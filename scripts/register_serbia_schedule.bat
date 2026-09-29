@echo off
rem ============================================================
rem 注册 Serbia pipeline Windows 计划任务（每日 06/12/18/24 点）
rem 以管理员身份运行本文件一次即可。
rem 注意：路径含空格需引号；本文件为 ASCII，规避非 ASCII 编码问题。
rem ============================================================

set PY=C:\Users\lwj93\.workbuddy\binaries\python\envs\default\Scripts\python.exe
set WORKDIR=C:\Users\lwj93\WorkBuddy\polybot

schtasks /Create /F /SC DAILY /MO 1 /ST 06:00 /TN "Polybot_Serbia_0600" /TR "\"%PY%\" \"%WORKDIR%\scripts\run_serbia_pipeline.py\""
schtasks /Create /F /SC DAILY /MO 1 /ST 12:00 /TN "Polybot_Serbia_1200" /TR "\"%PY%\" \"%WORKDIR%\scripts\run_serbia_pipeline.py\""
schtasks /Create /F /SC DAILY /MO 1 /ST 18:00 /TN "Polybot_Serbia_1800" /TR "\"%PY%\" \"%WORKDIR%\scripts\run_serbia_pipeline.py\""
schtasks /Create /F /SC DAILY /MO 1 /ST 23:55 /TN "Polybot_Serbia_2355" /TR "\"%PY%\" \"%WORKDIR%\scripts\run_serbia_pipeline.py\""

echo.
echo Registered 4 daily runs. Verify with: schtasks /Query /TN Polybot_Serbia_0600
pause

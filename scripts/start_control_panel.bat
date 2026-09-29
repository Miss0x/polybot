@echo off
rem 启动 Polybot 本地控制面板（http://127.0.0.1:8787）
rem 浏览器由服务启动后自动打开，无需手动操作
rem 如需开机自启：把本文件的快捷方式放进 shell:startup 文件夹

cd /d C:\Users\lwj93\WorkBuddy\polybot
"C:\Users\lwj93\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m polybot.webapp.server

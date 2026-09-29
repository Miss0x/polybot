@echo off
rem 启动 Polybot 本地控制面板（http://127.0.0.1:8787）
rem 可双击运行；如需开机自启，把本文件的快捷方式放进 shell:startup 文件夹

start "" http://127.0.0.1:8787
"C:\Users\lwj93\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m polybot.webapp.server

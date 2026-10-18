@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在启动财务岗位聚合界面（关闭本窗口即退出）...
python -m streamlit run app.py
pause

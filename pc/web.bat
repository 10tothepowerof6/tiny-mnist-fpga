@echo off
rem Bam dup chuot vao file nay de mo trang web TinyML
cd /d "%~dp0"
py tinyml_web.py
if errorlevel 1 python tinyml_web.py
if errorlevel 1 pause

@echo off
rem Bam dup chuot vao file nay de mo trang xem ket qua mo phong
cd /d "%~dp0"
py tinyml_viewer.py
if errorlevel 1 python tinyml_viewer.py
if errorlevel 1 (
  echo.
  echo Khong chay duoc. Kiem tra da cai Python tu python.org chua ^(nho tick "Add python.exe to PATH"^).
  pause
)

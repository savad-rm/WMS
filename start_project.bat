@echo off
@REM cd /d "C:\path\to\your\project"
call venv\Scripts\activate
python manage.py runserver
pause

@echo off
if not exist .env (echo .env yoq: .env.example dan nusxa oling & exit /b 1)
python manage.py migrate
python manage.py runserver 0.0.0.0:8000

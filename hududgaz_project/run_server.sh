#!/usr/bin/env bash
# Git Bash / Linux / macOS: serverni ishga tushirish
set -e
[ -f .env ] || { echo ".env yo'q: .env.example dan nusxa oling"; exit 1; }
python manage.py migrate
python manage.py runserver 0.0.0.0:8000

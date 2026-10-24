#!/usr/bin/env bash
set -e
[ -f .env ] || { echo ".env yo'q: .env.example dan nusxa oling"; exit 1; }
python manage.py runbot

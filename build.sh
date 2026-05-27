#!/usr/bin/env bash
# Render build script for Django backend
set -e

pip install -r backend/requirements.txt

cd backend
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py seed_demo --password "$DEMO_PASSWORD"

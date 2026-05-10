#!/bin/bash
set -e
python manage.py migrate
python manage.py load_test_data
python manage.py collectstatic --noinput
gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2

#!/bin/bash
# Local test command:
# cd "/Users/robert/Documents/Coding/1. Render/cg_data_exchange"
# /Users/robert/anaconda3/envs/env_python_django/bin/python manage.py test --keepdb 2>&1
set -e
python manage.py migrate
python manage.py load_test_data
python manage.py collectstatic --noinput
gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2

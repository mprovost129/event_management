web: gunicorn config.wsgi:application
worker: celery -A config worker --loglevel=INFO
beat: celery -A config beat --loglevel=INFO
release: python manage.py migrate

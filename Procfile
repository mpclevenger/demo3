web: gunicorn wsgi:app --worker-class gthread --threads 4 --timeout 60 --access-logfile -
release: python manage.py migrate

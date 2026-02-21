web: python3 manage.py migrate && python3 manage.py collectstatic --no-input && gunicorn djangoapp.yapify.wsgi
worker: python3 manage.py qcluster
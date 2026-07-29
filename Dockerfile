FROM python:3.13-slim

ARG REQUIREMENTS_FILE=requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r "${REQUIREMENTS_FILE}"

RUN addgroup --system app && adduser --system --ingroup app app

COPY --chown=app:app . .
RUN mkdir -p /app/logs /app/media /app/staticfiles \
    && chown -R app:app /app/logs /app/media /app/staticfiles

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health/live/', timeout=3).read()"

CMD ["sh", "-c", "python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --access-logfile - --error-logfile -"]

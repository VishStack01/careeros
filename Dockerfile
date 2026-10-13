# CareerOS Cloud: one image for the web app, the worker and migrations.
#   docker build -t careeros .
#   docker run careeros careeros cloud serve --host 0.0.0.0     (web, the default)
#   docker run careeros careeros cloud worker                   (background worker)
#   docker run careeros careeros cloud migrate                  (release step)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UPLOAD_DIR=/data/uploads
WORKDIR /app

COPY pyproject.toml README.md ./
COPY careeros ./careeros
RUN pip install ".[cloud]" \
 && useradd --create-home --uid 10001 careeros \
 && mkdir -p /data/uploads && chown -R careeros /data

USER careeros
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)" || exit 1
CMD ["careeros", "cloud", "serve", "--host", "0.0.0.0", "--port", "8000"]

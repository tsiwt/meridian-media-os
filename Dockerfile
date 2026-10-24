FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    DB_PATH=/data/meridian.db \
    SEED_ON_BOOT=1

WORKDIR /app

RUN groupadd --system --gid 10001 meridian \
    && useradd --system --uid 10001 --gid meridian --home-dir /app --shell /usr/sbin/nologin meridian

COPY app ./app
COPY web ./web
COPY docs ./docs
COPY samples ./samples
COPY README.md ./README.md
COPY README.md /README.md

RUN mkdir -p /data /app/data \
    && chown -R meridian:meridian /data /app

USER meridian

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=4).status == 200 else 1)"]

CMD ["python", "-m", "app.server"]

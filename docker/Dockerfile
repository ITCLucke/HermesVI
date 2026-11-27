FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8800 \
    HF_HOME=/models XDG_CACHE_HOME=/models DATA_DIR=/data
WORKDIR /app

# Optionale Zusatzpakete, z. B.: docker compose build --build-arg EXTRA_PIP="faster-whisper"
ARG EXTRA_PIP=""
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt ${EXTRA_PIP} \
 && useradd -r -u 10001 hermesvi \
 && mkdir -p /models /data && chown hermesvi /models /data && chmod 700 /data

COPY server.py extract.py ./
# static/ wird aus ../ui erzeugt: node scripts/sync-ui.mjs (macht der Release-Build automatisch)
COPY static ./static

USER hermesvi
EXPOSE 8800
HEALTHCHECK --interval=30s --timeout=4s --start-period=60s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8800/health',timeout=3).status==200 else 1)"
CMD ["python", "server.py"]

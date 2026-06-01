FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 app

WORKDIR /app

# Layer 1: dependencies (cached until requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2: application code
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini VERSION entrypoint.sh .

RUN chmod +x entrypoint.sh

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import http.client; c=http.client.HTTPConnection('localhost',8000); c.request('GET','/health'); r=c.getresponse(); exit(0) if r.status==200 else exit(1)"

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

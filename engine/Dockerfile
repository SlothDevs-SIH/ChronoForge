# Build from the repository root:  docker build -f engine/Dockerfile .   (Render: Dockerfile path engine/Dockerfile, context .)
# Layout inside the image matches the repository (/srv/engine/app, /srv/data, /srv/demo, /srv/contract) because the code
# finds data/models, demo/photos and contract/ relative to the repo root.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 trueclose

WORKDIR /srv/engine
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/app ./app
COPY contract /srv/contract
COPY data/models /srv/data/models
COPY data/processed /srv/data/processed
COPY demo/photos /srv/demo/photos

# The warehouse is NOT baked in: bootstrap downloads it from WAREHOUSE_URL into WAREHOUSE_DIR (a persistent disk).
ENV CONTRACT_DIR=/srv/contract \
    WAREHOUSE_DIR=/var/data/warehouse \
    SAT_CACHE_DIR=/var/data/cache/satellite \
    PYTHONUNBUFFERED=1 \
    PORT=8001
RUN mkdir -p /var/data/warehouse /var/data/cache/satellite && chown -R trueclose /var/data /srv
USER trueclose
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD curl -fsS http://localhost:${PORT}/health || exit 1
CMD ["python", "-m", "app.bootstrap"]

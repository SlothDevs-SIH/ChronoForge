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

# ENGINE_DUCKDB_PATH / ENGINE_MEMORY_LIMIT keep the ticket tables in a scratch file with at most 200 MB in RAM: the Engine then
# peaks near 320 MB instead of 570 MB, so it fits a 512 MB host. Remove those three to hold everything in memory on a big host.
# ENGINE_BENGALURU_FROM loads only Bengaluru tickets created from 2024-10-01 (180,263 of 733,721): the citizen-reopen label, the only
# ground truth, exists from then. Remove it to load every Bengaluru ticket.
# The warehouse is NOT baked in: bootstrap downloads it from WAREHOUSE_URL into WAREHOUSE_DIR (a persistent disk).
ENV CONTRACT_DIR=/srv/contract \
    WAREHOUSE_DIR=/var/data/warehouse \
    SAT_CACHE_DIR=/var/data/cache/satellite \
    ENGINE_DUCKDB_PATH=/tmp/engine.duckdb \
    ENGINE_MEMORY_LIMIT=200MB \
    ENGINE_THREADS=2 \
    ENGINE_BENGALURU_FROM=2024-10-01 \
    PYTHONUNBUFFERED=1 \
    PORT=8001
RUN mkdir -p /var/data/warehouse /var/data/cache/satellite && chown -R trueclose /var/data /srv
USER trueclose
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD curl -fsS http://localhost:${PORT}/health || exit 1
CMD ["python", "-m", "app.bootstrap"]

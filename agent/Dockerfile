# Agent service image. Build context is the REPO ROOT (the Agent also reads the demo photos under demo/):
#   docker build -f agent/Dockerfile -t trueclose-agent .
# Render / any host: set the environment variables listed in agent/.env.example. The server listens on $PORT (default 8002).
FROM python:3.11-slim

# gosu lets the entrypoint fix ownership of a mounted disk (Render disks mount as root) and then drop to a normal user
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /srv
COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# CLIP is optional: build with --build-arg WITH_CLIP=1 (adds ~2 GB of torch; needs a host with several GB of RAM)
ARG WITH_CLIP=0
COPY agent/requirements-clip.txt .
RUN if [ "$WITH_CLIP" = "1" ]; then pip install --no-cache-dir -r requirements-clip.txt; fi

COPY agent/app app
COPY agent/sql sql
COPY demo demo
COPY agent/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /data && chown -R app:app /data

# SQLite and file paths only matter when DATABASE_URL is not set; the photo index (duplicate detection) lives on /data
ENV REPO_ROOT=/srv AGENT_DB=/data/agent.db PHOTO_INDEX=/data/photo_index.json UPLOAD_DIR=/data/uploads TRUST_PROXY=1 PORT=8002
VOLUME /data
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8002'), timeout=4)" || exit 1
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8002} --proxy-headers --forwarded-allow-ips='*'"]

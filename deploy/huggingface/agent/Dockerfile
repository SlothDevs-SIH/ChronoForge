# Agent on Hugging Face Spaces. The Space repo holds only this file and README.md; the code is pulled from the public
# GitHub repo at build time. To ship a new version: Space > Settings > Factory rebuild.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 user

ARG REPO_URL=https://github.com/SlothDevs-SIH/ChronoForge.git
ARG REPO_REF=main
WORKDIR /srv
RUN git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /tmp/repo \
    && cp -r /tmp/repo/agent/app ./app \
    && cp -r /tmp/repo/agent/sql ./sql \
    && cp /tmp/repo/agent/requirements.txt . \
    && cp -r /tmp/repo/demo ./demo \
    && rm -rf /tmp/repo
RUN pip install --no-cache-dir -r requirements.txt

# With DATABASE_URL set (Supabase Postgres) these local paths only hold the duplicate-photo index and cached files.
ENV REPO_ROOT=/srv \
    AGENT_DB=/home/user/data/agent.db \
    PHOTO_INDEX=/home/user/data/photo_index.json \
    UPLOAD_DIR=/home/user/data/uploads \
    AGENT_PHOTO_DIR=/home/user/data/citizen_photos \
    TRUST_PROXY=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860
RUN mkdir -p /home/user/data && chown -R user:user /home/user /srv
USER user
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]

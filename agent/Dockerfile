# Build context is the repo root (see docker-compose.yml): docker compose build agent
FROM python:3.11-slim
WORKDIR /srv
COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# CLIP is optional: build with --build-arg WITH_CLIP=1 (adds ~2 GB of torch)
ARG WITH_CLIP=0
COPY agent/requirements-clip.txt .
RUN if [ "$WITH_CLIP" = "1" ]; then pip install --no-cache-dir -r requirements-clip.txt; fi
COPY agent/app app
COPY agent/sql sql
ENV AGENT_DB=/data/agent.db PHOTO_INDEX=/data/photo_index.json
VOLUME /data
EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

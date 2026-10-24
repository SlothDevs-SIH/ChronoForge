# Engine on Hugging Face Spaces. The Space repo holds only this file and README.md; the code is pulled from the public
# GitHub repo at build time. To ship a new version: Space > Settings > Factory rebuild.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 user

ARG REPO_URL=https://github.com/SlothDevs-SIH/ChronoForge.git
ARG REPO_REF=main
WORKDIR /srv/engine
# The code finds data/models, demo/photos and contract/ relative to the repo root, so the layout under /srv mirrors the repo.
RUN git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /tmp/repo \
    && cp -r /tmp/repo/engine/app ./app \
    && cp /tmp/repo/engine/requirements.txt . \
    && mkdir -p /srv/data /srv/demo \
    && cp -r /tmp/repo/contract /srv/contract \
    && cp -r /tmp/repo/data/models /srv/data/models \
    && cp -r /tmp/repo/data/processed /srv/data/processed \
    && cp -r /tmp/repo/demo/photos /srv/demo/photos \
    && rm -rf /tmp/repo
RUN pip install --no-cache-dir -r requirements.txt

# The warehouse is not in the image: bootstrap downloads it from the WAREHOUSE_URL secret at start. Spaces have no
# persistent disk unless you add one, so it is fetched again after every restart.
ENV CONTRACT_DIR=/srv/contract \
    WAREHOUSE_DIR=/home/user/data/warehouse \
    SAT_CACHE_DIR=/home/user/data/cache/satellite \
    PYTHONUNBUFFERED=1 \
    PORT=7860
RUN mkdir -p /home/user/data/warehouse /home/user/data/cache/satellite && chown -R user:user /home/user /srv
USER user
EXPOSE 7860
CMD ["python", "-m", "app.bootstrap"]

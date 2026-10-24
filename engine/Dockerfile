FROM python:3.12-slim
WORKDIR /srv
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine/app ./app
COPY contract /srv/contract
ENV CONTRACT_DIR=/srv/contract
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

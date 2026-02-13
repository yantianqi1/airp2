FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json /frontend/package.json
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm install

COPY frontend /frontend

RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt \
    && pip install fastapi uvicorn[standard]

COPY . /app
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

EXPOSE 8011

CMD ["uvicorn", "api.rp_query_api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8011"]

# Multi-stage build: compila frontend Vite y sirve con FastAPI en una sola imagen

# 1) Build del frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps=false

COPY frontend/ ./
# Permite inyectar la URL de la API al build de Vite
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# 2) Imagen final con FastAPI + artefactos del frontend
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000

WORKDIR /app

# Dependencias del sistema mínimas (psycopg2-binary usa libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

# Código de la aplicación
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY README.md ./README.md
COPY docs/ ./docs/

# Artefactos del frontend generados en la etapa previa
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE ${PORT}

# uvicorn necesita que el puerto respete la variable PORT (Azure la inyecta)
CMD ["sh", "-c", "uvicorn downloader_qbench_data.api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]

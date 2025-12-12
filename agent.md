# Contexto del Proyecto: MCRLabs Dashboard

## Resumen
Sistema de visualización de datos de laboratorio que unifica flujos heredados (QBench) y nuevos flujos basados en Google Sheets (GLIMS). Consta de un backend en Python (FastAPI) que sincroniza datos hacia PostgreSQL y un frontend en React.

## Stack Tecnológico
- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Pandas, httpx, gspread.
- **Frontend:** React, TypeScript, Vite (Puerto dev: 5177).
- **Base de Datos:** PostgreSQL 15 (Docker service: `db`, Puerto: 5432).
- **Infraestructura:** Docker Compose.

## Arquitectura y Flujos de Datos

### 1. Flujo GLIMS (Google Sheets)
- **Fuente:** Google Sheets accedido vía Service Account.
- **Sincronización:** Script `scripts/run_sync_glims.py`.
- **Lógica de Sync:**
  - **Idempotencia:** Upserts basados en `sample_id`.
  - **Limpieza de Datos:** Valores como `ND`, `BQL`, `N/A`, `<50` o cadenas vacías se convierten a `NULL` en campos numéricos.
  - **Fechas:** Se normalizan como `date` (sin zona horaria) para reflejar el valor exacto de la hoja de cálculo.
  - **Relaciones:** Muestras se vinculan a `glims_dispensaries` por coincidencia de nombre.

### 2. Flujo QBench (Legacy)
- **API:** Endpoints bajo `/api/v1`.
- **Datos:** Estructura clásica de Orders, Samples, Tests y Batches.

## Convenciones de Código y Negocio

### API y Endpoints
- **Versiones:**
  - `/api/v1`: Endpoints heredados de QBench (Métricas generales, TAT, Throughput).
  - `/api/v2`: Endpoints específicos de GLIMS (`/api/v2/glims/overview`).
- **Formatos:**
  - Fechas y horas en API: ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`).
  - Decimales: Punto (`.`) como separador.

### Métricas y Terminología
- **TAT (Turnaround Time):** Reemplaza el concepto de SLA. Target por defecto: 72 horas.
- **Reports:** En el contexto de GLIMS, se refiere a "Samples reported".
- **Analytes:** Las tablas de resultados (`glims_*_results`) contienen una columna `analytes` (JSON/Texto) además de columnas numéricas limpias.

## Estructura de Base de Datos (GLIMS)
Tablas con prefijo `glims_*`:
- `glims_dispensaries`: Clientes.
- `glims_samples`: Muestras principales.
- `glims_[tipo]_results`: Tablas de resultados (ej. `glims_cn_results`, `glims_mb_results`).

## Comandos Frecuentes

### Backend
```bash
# Levantar API
python scripts/run_api.py --host 0.0.0.0 --port 8000

# Sincronizar GLIMS (Incremental)
python scripts/run_sync_glims.py

# Sincronizar GLIMS (Full Refresh - Útil tras cambios en columnas)
python scripts/run_sync_glims.py --ignore-lookback
```

## Archivos de Referencia
- Definición completa de endpoints v1: `docs/endpoint-data.txt`
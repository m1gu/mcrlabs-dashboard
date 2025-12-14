# GLIMS status tracking: fases 0 y 1

## Fase 0 — Alineación y supuestos resueltos
- Apps Script llamará a endpoints del backend (no acceso directo a la BD).
- Timestamps se almacenan en UTC (`timestamptz`); `changed_at` puede venir en el payload o se usa `now()` en el backend.
- `date_received` exacto se captura sólo a partir de la activación del trigger (no retroactivo).
- Status válidos (catálogo inicial): `Sample Received`, `Generating`, `Needs Second Check`, `Second Check Done`, `Reported`, `Needs METRC Upload`.
- Tabs a vigilar: `Overview` (columna `Status`) y `Dispensaries` (columna `Dispensary` para nuevos clientes).
- App Script enviará `sample_id` tal cual el Sheet; backend normalizará y validará que el sample exista antes de registrar eventos.

## Fase 1 — Esquema y endpoints backend

### Tablas nuevas
```sql
-- Eventos inmutables de cambios de estado por sample
CREATE TABLE glims_samples_status_events (
    id              BIGSERIAL PRIMARY KEY,
    sample_id       TEXT NOT NULL REFERENCES glims_samples(sample_id),
    status          TEXT NOT NULL,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL DEFAULT 'apps_script',
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_gsse_sample_changed_at ON glims_samples_status_events (sample_id, changed_at);
CREATE INDEX idx_gsse_status_changed_at ON glims_samples_status_events (status, changed_at);

-- Sugerencias de nuevos dispensaries capturadas desde el Sheet
CREATE TABLE glims_dispensaries_ingest (
    id                  BIGSERIAL PRIMARY KEY,
    sheet_line_number   INTEGER NOT NULL,
    name                TEXT NOT NULL,
    name_normalized     TEXT GENERATED ALWAYS AS (LOWER(TRIM(name))) STORED,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source              TEXT NOT NULL DEFAULT 'apps_script',
    processed           BOOLEAN NOT NULL DEFAULT false,
    approved            BOOLEAN NOT NULL DEFAULT false,
    notes               TEXT
);
CREATE UNIQUE INDEX uq_gdi_name_norm ON glims_dispensaries_ingest (name_normalized);
CREATE UNIQUE INDEX uq_gdi_sheet_line ON glims_dispensaries_ingest (sheet_line_number);
```

### Endpoints API v2 (protegidos, pensados para Apps Script)
- `POST /api/v2/glims/status-events`
  - Payload: `{ "sample_id": "string", "status": "Sample Received|Generating|Needs Second Check|Second Check Done|Reported|Needs METRC Upload", "changed_at": "2025-01-12T15:04:05Z"?, "metadata": { ... }? }`
  - Validaciones: sample debe existir en `glims_samples`; normalizar `sample_id` (trim) y `status` (title case); si `changed_at` falta, usar `now()` UTC.
  - Comportamiento: inserta en `glims_samples_status_events`. Idempotencia opcional vía hash `(sample_id, status, changed_at)` si se añade constraint única.
  - Respuestas: `201` con `{id, sample_id, status, changed_at}`; `404` si sample no existe; `400` si status inválido.

- `POST /api/v2/glims/dispensaries/suggest`
  - Payload: `{ "name": "ACME Dispensary", "sheet_line_number": 42 }`
  - Validaciones: rechazar si ya existe en `glims_dispensaries` (comparar `LOWER(TRIM(name))`); rechazar si ya existe en `glims_dispensaries_ingest` con mismo nombre normalizado o línea.
  - Comportamiento: inserta registro en ingest y devuelve `201`; en caso de existencia, `409` con razón.

- (Opcional) `GET /api/v2/glims/status-events?sample_id=...` y `GET /api/v2/glims/dispensaries/ingest` para debug/ops.

### Notas de integración con dashboard/TAT
- Las métricas de TAT/Open Time deben migrar a usar `glims_samples_status_events` (primer `Reported` - primer `Sample Received`; open time = `now` - último estado no final).
- Si se requiere rapidez, crear vista materializada derivada que obtenga el primer timestamp por estado por sample, refrescada tras inserciones.

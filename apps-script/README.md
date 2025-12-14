# Apps Script: GLIMS status monitor

Proyecto Apps Script standalone para vigilar el Spreadsheet GLIMS y enviar eventos al backend (API v2). El código se versiona aquí, pero el runtime vive en la plataforma de Google Apps Script.

## Prerrequisitos
- Node.js y npm instalados (para `clasp`).
- Acceso al Spreadsheet (ID) y al backend con los endpoints v2 ya expuestos:
  - `POST /api/v2/glims/status-events`
  - `POST /api/v2/glims/dispensaries/suggest`
- Token/API key para el backend.

## Configuración local (clasp)
1) Instalar CLI:
```bash
npm install -g @google/clasp
```
2) Autenticarse en Google:
```bash
clasp login
```
3) Crear proyecto standalone en Apps Script:
```bash
clasp create --type standalone --title "GLIMS Status Monitor"
```
Esto genera `.clasp.json` en la carpeta actual (no se commitea el ID del proyecto hasta que lo crees).

4) Empaquetar y subir el código:
```bash
clasp push
```
Si ya existe el proyecto y quieres traer la versión remota: `clasp pull`.

## Configuración en Apps Script (UI)
1) Abrir el proyecto en script.google.com (botón “Open in Apps Script” luego de `clasp create` o desde la UI).
2) En “Project Settings”:
   - Activar V8 runtime.
   - Guardar Script Properties:
     - `API_BASE_URL` (ej: `https://api.tu-dominio.com`)
     - `API_TOKEN` (bearer token o API key)
     - `SPREADSHEET_ID` (ID del Sheet GLIMS)
     - `OVERVIEW_TAB` (ej: `Overview`)
     - `DISPENSARIES_TAB` (ej: `Dispensaries`)
     - `STATUS_HEADER` (ej: `Status`)
     - `SAMPLE_ID_HEADER` (ej: `SampleID`)
     - `DISPENSARY_HEADER` (ej: `Dispensary`)

## Despliegue de triggers
Desde la UI de Apps Script:
1) Ir a Triggers (Reloj) → “Add Trigger”.
2) Seleccionar función: `onEdit`.
3) Event source: “From spreadsheet”.
4) Event type: “On edit”.
5) Guardar.

Opcional: agregar un trigger “time-driven” (ej: cada 15 minutos) para implementar reintentos si decides almacenar fallos en Properties (el código de ejemplo no cola reintentos).

## Flujo cubierto
- Tab `Overview`: cambios en la columna `Status` envían `sample_id`, `status` y `changed_at` UTC a `/api/v2/glims/status-events`.
- Tab `Dispensaries`: nuevas ediciones en la columna `Dispensary` envían sugerencia a `/api/v2/glims/dispensaries/suggest` con `sheet_line_number`.

## Comandos rápidos
- Subir cambios: `clasp push`
- Traer desde Apps Script: `clasp pull`
- Ver deployments: `clasp deployments`
- Crear nueva versión: `clasp version "mensaje"`

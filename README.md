# Downloader QBench Data
   ```
Aplicacion Python para descargar y mantener sincronizada la informacion de QBench en una base de datos PostgreSQL local. Actualmente cubre la descarga de **customers**, **orders**, **samples**, **tests** y **batches** con soporte para cargas completas e incrementales, incluyendo checkpoints y manejo de errores.
   ```
## Tecnologias principales
- Python 3.12+
- [httpx](https://www.python-httpx.org/) para consumo de la API QBench
- [SQLAlchemy](https://www.sqlalchemy.org/) y PostgreSQL para persistencia
- [pandas](https://pandas.pydata.org/) (planeado para validaciones)
- [PySide6](https://doc.qt.io/qtforpython/) (fase posterior para UI manual)
- [FastAPI](https://fastapi.tiangolo.com/) para exponer los datos sincronizados
- React + TypeScript (dashboard web responsive)
   ```
## Requisitos previos
1. Python 3.12 instalado y disponible en `PATH`.
2. PostgreSQL accesible (local o remoto) con el rol/base configurados.
3. Credenciales QBench validas (ID, secret y endpoint de token).
4. [git](https://git-scm.com/) si vas a clonar/colaborar.
   ```
## Instalacion y configuracion
```bash
# Crear y activar entorno virtual (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate
   ```
# Instalar dependencias
pip install -r requirements.txt
   ```
# Configurar variables de entorno (copiar .env.example)
copy .env.example .env
# editar .env con credenciales QBench y datos de PostgreSQL
# variables opcionales:
#   SYNC_LOOKBACK_DAYS=7        # horizonte por defecto (en dÃ­as) para el pipeline de sincronizaciÃ³n ventana
#   PAGE_SIZE=50                # tamaÃ±o base de pÃ¡gina (el valor real no excederÃ¡ el mÃ¡ximo permitido por QBench)
#   AUTH_TOKEN_TTL_HOURS=3      # vigencia (horas) del token de autenticacion
# variables obligatorias adicionales:
#   AUTH_SECRET_KEY=coloca_un_valor_unico_y_secreto
```
   ```
## Gestion de usuarios del dashboard

La autenticacion del dashboard se administra con una tabla aislada (`users`). Para prepararla:

1. Ejecuta el script SQL `docs/sql/create_users_table.sql` en tu base PostgreSQL (Query Tool de pgAdmin o `psql -f`). Crea la tabla y el trigger que mantiene `updated_at`.
2. Usa el script `scripts/manage_users.py` para crear cuentas o restablecer contraseñas. Las contraseñas deben tener al menos 10 caracteres e incluir minusculas, mayusculas y digitos; se almacenan cifradas con `bcrypt`.

```bash
# Crear usuario (solicita contraseña de forma interactiva si se omite el flag)
python scripts/manage_users.py create --username admin

# Restablecer contraseña y limpiar bloqueos
python scripts/manage_users.py reset-password --username admin --unlock

# Pasar la contraseña por argumento (evita guardarla en historial compartido)
python scripts/manage_users.py create --username ops --password "Str0ngPass123"
```

> La administracion se realiza exclusivamente via este script; el frontend no ofrece registro ni recuperacion.

## Lista de entidades bloqueadas (banlist)

Para ocultar entidades especificas en la API (customers, orders, samples, batches, tests) usa la tabla `banned_entities`. Las entidades bloqueadas no apareceran en los endpoints de detalle; si una orden es bloqueada, sus samples/tests tambien se omiten.

Ejemplos con el CLI:

```bash
# Bloquear una orden
python scripts/manage_banlist.py add --type order --id 12345 --reason "QA requested hide"

# Bloquear un test
python scripts/manage_banlist.py add --type test --id 55506

# Desbloquear
python scripts/manage_banlist.py remove --type order --id 12345
```

### Autenticacion via API
- Endpoint: `POST /api/auth/login` (body con `username` y `password`).
- Respuesta: token `bearer` con vigencia configurable (`AUTH_TOKEN_TTL_HOURS`, por defecto 3 horas).
- Para acceder a `/api/v1/...` debes enviar `Authorization: Bearer <token>` en cada solicitud; al expirar, solicita uno nuevo.
- Tras 3 intentos fallidos el usuario queda bloqueado por 24 horas (se desbloquea con `--unlock` en el script).

## Estructura del proyecto
```
Downloader-Qbench-Data/
|-- docs/
|   `-- roadmap.md            # Plan de trabajo y notas
|-- scripts/
|   |-- run_sync_customers.py # Ejecuta sincronizacion de clientes (lista IDs omitidos)
|   |-- run_sync_orders.py    # Ejecuta sincronizacion de ordenes (lista IDs omitidos)
|   |-- run_sync_samples.py   # Ejecuta sincronizacion de muestras (lista IDs omitidos)
|   |-- run_sync_batches.py   # Ejecuta sincronizacion de batches (lista IDs omitidos)
|   |-- run_sync_tests.py     # Ejecuta sincronizacion de tests (lista IDs omitidos)
|   |-- run_sync_all.py       # Orquesta todas las entidades y reporta omitidos por entidad
|   |-- run_api.py            # Levanta la API REST
|   `-- fetch_single_entity.py # Descarga manualmente entidades puntuales por ID
|-- src/
|   `-- downloader_qbench_data/
|       |-- clients/          # Cliente HTTP QBench
|       |-- config.py         # Carga de configuracion y .env
|       |-- ingestion/        # Pipelines de ingesta
|       `-- storage/          # Modelos y acceso a base de datos
|-- tests/                    # Pruebas unitarias
|-- requirements.txt          # Dependencias del proyecto
|-- README.md                 # Este archivo
`-- .env.example              # Plantilla de variables de entorno
```
   ```
## Ejecucion
1. Asegurate de tener la base y credenciales configuradas en `.env`.
2. Activa el entorno virtual antes de ejecutar cualquier script (`.\.venv\Scripts\Activate` en PowerShell).
3. Lanza la sincronizacion de la entidad necesaria. Ejemplos de full refresh:
   ```bash
   python scripts/run_sync_all.py --full     # ejecuta todas las entidades en secuencia
   python scripts/run_sync_customers.py --full
   python scripts/run_sync_orders.py --full      # requiere customers
   python scripts/run_sync_samples.py --full     # requiere orders
   python scripts/run_sync_batches.py --full     # requiere customers/orders/samples
   python scripts/run_sync_tests.py --full       # requiere samples y batches
   python scripts/run_sync_window.py --days 7    # sincroniza ventana reciente (orden descendente) y genera reporte
   ```
   Omite `--full` para realizar sincronizaciones incrementales aprovechando el checkpoint almacenado.
   El comando `run_sync_window.py` mantiene un rango mÃ³vil actualizado sin recorrer todo el feed:
   - Usa `--days N` (o el valor por defecto `SYNC_LOOKBACK_DAYS`) para definir el horizonte.
   - Cada entidad se consulta ordenada por `date_created` descendente; cuando los registros estÃ¡n fuera del rango se detiene la paginaciÃ³n.
   - Cuando falta una dependencia (cliente/orden/muestra/test) intenta recuperarla sin salir del flujo, con un mÃ¡ximo de 3 intentos antes de registrar el elemento en `skipped`.
   - Genera un informe en `docs/sync_reports/sync_report_<fecha>.txt` con el total de nuevos registros por entidad y los IDs que no pudieron sincronizarse.
   El comando `run_sync_all.py` acepta argumentos adicionales, por ejemplo:
   ```bash
   python scripts/run_sync_all.py                 # incremental de todas las entidades
   python scripts/run_sync_all.py --entity orders --entity samples
   ```
   Al finalizar cada sync se imprime un bloque con los IDs omitidos y el motivo (dependencias faltantes, errores 400, etc.) para facilitar su correccion manual.
4. Levanta la API REST si necesitas exponer los datos sincronizados:
   ```bash
   python scripts/run_api.py --host 0.0.0.0 --port 8000
   ```
   Esto publica la documentacion interactiva en `http://localhost:8000/api/docs` y los endpoints REST descritos abajo.
5. Lanza el dashboard PySide6 (carga por defecto los ultimos 7 dias):
   ```bash
   python scripts/run_dashboard.py
   ```
   Puedes ajustar el backend usando la variable `DASHBOARD_API_BASE_URL` si el servicio corre en otro host.
6. Construye o desarrolla el dashboard web (React + TypeScript):
   ```bash
   cd frontend
   npm install          # solo la primera vez
   npm run dev          # modo desarrollo en http://localhost:5177
   npm run build        # genera frontend/dist para servirlo con FastAPI
   ```
   Opcional: define `API_BASE_URL=http://localhost:8000/api/v1` para apuntar a otra instancia durante el desarrollo.
   Cuando existe `frontend/dist`, la aplicacion FastAPI expone el dashboard en `http://localhost:8000/dashboard/` tras ejecutar `python scripts/run_api.py`.
7. Descarga entidades puntuales cuando necesites reprocesar IDs especificos:
   ```bash
   python scripts/fetch_single_entity.py test 12345
   python scripts/fetch_single_entity.py sample 67890 --skip-foreign-check
   ```
   El comando utiliza el `EntityRecoveryService`, de modo que trae dependencias faltantes en cascada y actualiza los checkpoints relacionados automáticamente.
   El comando inserta/actualiza la fila en la base, valida dependencias basicas y actualiza el checkpoint.
8. Verifica los registros en PostgreSQL (`customers`, `orders`, `samples`, `batches`, `tests`, `sync_checkpoints`).
### Sincronizacion de tests
- El pipeline usa el script `scripts/run_sync_tests.py` y crea/actualiza el checkpoint `sync_checkpoints.entity = 'tests'`.
- Solo se persistiran tests cuyo `sample_id` exista localmente; si falta se registra en el resumen y se omite.
- Durante la sincronizacion incremental se detiene automaticamente al encontrar registros ya sincronizados (`date_created` <= ultimo checkpoint).
- Cuando QBench no entrega metadatos clave (label, titulo, worksheet, bandera de reporte) el proceso realiza un `fetch_test` individual y guarda el contenido bruto en `tests.worksheet_raw`.
- Argumentos disponibles:
  - `--full`: fuerza un refresh completo, ignorando el checkpoint previo.
  - `--page-size`: sobrescribe el `page_size` configurado (maximo 50 por restricciones de la API).
- El script muestra progreso por pagina con `tqdm` y al finalizar imprime un resumen con totales procesados, omisiones y la ultima fecha sincronizada.
   ```
### API REST
- `GET /api/health`: verificacion rapida del servicio.
- `GET /api/v1/metrics/summary`: KPIs globales (samples, tests, customers, reports) y TAT promedio.
- `GET /api/v1/metrics/activity/daily`: serie diaria de samples/tests (con comparativo opcional del periodo previo).
- `GET /api/v1/metrics/samples/overview`: totales y distribuciones por estado/matrix filtrables por fecha, cliente y orden.
- `GET /api/v1/metrics/tests/overview`: conteos por estado y label de los tests con filtros opcionales por batch.
- `GET /api/v1/metrics/customers/new`: listado de clientes creados en el rango.
- `GET /api/v1/metrics/customers/top-tests`: top N clientes por tests en el rango.
- `GET /api/v1/metrics/tests/tat`: estadisticas de TAT (promedio, mediana, p95, distribucion y serie opcional por dia/semana).
- `GET /api/v1/metrics/tests/tat-breakdown`: detalle de TAT agrupado por label_abbr.
- `GET /api/v1/metrics/reports/overview`: resumen de reportes dentro/fuera del SLA (filtrado por `report_completed_date` y estado `REPORTED`).
- `GET /api/v1/metrics/tests/tat-daily`: serie diaria de TAT con desglose dentro/fuera de SLA y promedio movil.
- `GET /api/v1/metrics/common/filters`: catalogos basicos (clientes, estados) para poblar dashboards.
- `GET /api/v1/entities/samples/{sample_id}`: detalle de una muestra con orden/batches relacionados.
- `GET /api/v1/entities/tests/{test_id}`: detalle de un test con sample/batches.

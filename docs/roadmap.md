# Proyecto Downloader QBench Data

## 1. Objetivo General
- Ingestar y respaldar toda la informacion disponible de QBench para una unica empresa en una base de datos PostgreSQL local.
- Ejecutar cargas manuales posteriores que incorporen solo los cambios nuevos desde el ultimo respaldo exitoso.
- Exponer una interfaz grafica PySide6 con un boton "ACTUALIZAR" y un indicador de la fecha del ultimo respaldo.
- En una fase posterior, ofrecer un API REST (FastAPI) que sirva los datos consolidados para consumo externo (por ejemplo dashboards en otra aplicacion de Python).

## 2. Supuestos y Dependencias
- Credenciales QBench administradas mediante variables de entorno o archivo `.env` (nunca en texto plano en el repositorio).
- Acceso a la documentacion completa de los endpoints: Customers, Orders, Samples, Batches, Tests, Assay, Reports.
- El API de QBench soporta paginacion (page, per_page) y filtros por fecha (`updated_at` o similar). Si no existe filtro, se definira un cursor local.
- PostgreSQL local disponible; se utilizara SQLAlchemy como capa de acceso.
- El proceso de sincronizacion sera manual hasta nuevo aviso.
- Actualmente no se cuenta con acceso a internet en este entorno, por lo que la documentacion debera copiarse localmente para revisar campos exactos.

## 3. Arquitectura Propuesta
### 3.1 Componentes
- `clients.qbench`: cliente HTTP (httpx o requests) con autenticacion, paginacion, manejo de limites de tasa y backoff exponencial.
- `ingestion.pipeline`: orquestador que solicita datos, valida con pandas y ejecuta la persistencia transaccional en PostgreSQL.
- `storage.models`: modelos SQLAlchemy, reglas de upsert y migraciones (alembic later).
- `storage.checkpoints`: acceso a la tabla `sync_checkpoints` para leer y escribir estado por entidad.
- `ui.app`: aplicacion PySide6 con boton "ACTUALIZAR", indicador de ultima sincronizacion, y vista de ultimos logs.
- `api.server`: servicio FastAPI con endpoints de lectura y, opcionalmente, uno para disparar sincronizaciones.
- `logging`: configuracion centralizada con archivo rotativo y correlacion via `run_id`.

### 3.2 Flujo General
1. El usuario pulsa "ACTUALIZAR" en la UI.
2. Se lanza un hilo (QThread) que invoca `ingestion.run()` con la lista de entidades a sincronizar.
3. Para cada entidad:
   - Se lee el checkpoint (`last_synced_at`, `last_cursor`).
   - Se consumen paginas del API respetando limites.
   - Se valida la estructura con pandas (tipos, nulos criticos).
   - Se ejecuta un UPSERT por `qbench_id` dentro de una transaccion.
   - Se actualiza el checkpoint tras cada pagina exitosa.
4. Al finalizar, se actualiza el indicador en la UI y se registra el resultado en `ingestion_runs`.
5. Si ocurre un fallo, se hace rollback, se registra estado `failed` con mensaje y se notifica en UI/logs.

### 3.3 Manejo de Fallos
- Reintentos con backoff para errores 5xx o 429.
- Fallos 4xx cancelan la corrida y se registran para analisis.
- Posibilidad de guardar respuesta cruda en tabla `staging_raw` o archivos temporales para depuracion.
- Logs estructurados (JSON opcional) para facilitar diagnostico.

## 4. Modelo de Datos Inicial (resumen)
- `customers`: `qbench_id` PK, datos principales, `updated_at`, `fetched_at`.
- `orders`: `qbench_id`, `customer_id`, estados, fechas clave, `metadata` JSONB.
- `samples`: `qbench_id`, `order_id`, tipo, `updated_at`.
- `batches`: `qbench_id`, `sample_id`, estado, `updated_at`.
- `tests`: `qbench_id`, `batch_id`, `assay_id`, estado, `completed_at`, `updated_at`.
- `assays`: `qbench_id`, nombre, version, `updated_at`.
- `reports`: `qbench_id`, referencias a order/batch/test, `published_at`, `updated_at`.
- `sync_checkpoints`: entidad, `last_synced_at`, `last_cursor`, `status`, `message`, `updated_at`.
- `ingestion_runs`: id, entidad, inicio, fin, filas procesadas, estado, error.

*(Campos definitivos se ajustaran al revisar la documentacion oficial.)*

## 5. Estrategia de Sincronizacion
### 5.1 Carga Inicial
- Ejecutar cada entidad sin filtro de fecha (cuando sea posible) en lotes controlados.
- Usar transacciones por lote y upserts para tolerar ejecuciones repetidas.

### 5.2 Carga Incremental
- Usar `updated_at >= last_synced_at` para filtrar.
- Si no existe filtro, usar `last_cursor` (pagina + offset) y validar contra IDs locales antes del upsert.
- Registrar `fetched_at` con timestamp local para trazabilidad.

### 5.3 Checkpoints
- Guardar progreso despues de cada pagina: `last_synced_at`, `last_cursor`, `status`, `message`.
- Al completar la entidad, marcar `status = completed` y guardar conteo de filas.
- Ante fallos, mantener `status = failed` y reintentar desde el checkpoint anterior.

### 5.4 Resiliencia
- Manejar limites de tasa con tiempo de espera dinamico.
- Capturar y registrar cambios de esquema (campos inesperados) en una columna JSON adicional.
- Configurar alertas simples en UI (por ejemplo cambiar color del indicador o mostrar dialogo).

## 6. Plan de Trabajo Detallado
### Fase 0 - Preparacion (Dia 1)
- Crear estructura de carpetas (`src`, `tests`, `docs`, `scripts`).
- Definir gestion de configuracion (`.env`, `pydantic-settings` o similar).
- Agregar `requirements.txt` o `pyproject.toml` con dependencias base (PySide6, FastAPI, SQLAlchemy, pandas, httpx, python-dotenv, psycopg2-binary, loguru o logging).
- Documentar configuracion de PostgreSQL local (docker compose opcional).

### Fase 1 - Cliente QBench y Customers (Dias 2-3)
- Implementar `QBenchClient` con autenticacion, paginacion y reintentos.
- Crear modelos SQLAlchemy para `customers`, `sync_checkpoints`, `ingestion_runs`.
- Construir pipeline `sync_customers` (full + incremental) y pruebas unitarias con mocks de API.
- Validar que el checkpoint se actualice correctamente tras cada pagina.

### Fase 2 - Orders (Dias 4-5)
- Extender modelos y pipeline para `orders`, vinculando `customer_id`.
- Gestionar dependencias: cargar `customers` antes de `orders`.
- Probar reintentos y manejo de inconsistencia (orden sin cliente -> registro pendiente o log de error).

### Fase 3 - Samples, Batches, Tests, Assays, Reports (Semana 2-3)
- Implementar secuencialmente cada entidad respetando la cadena de dependencia.
- Agregar validaciones cruzadas (por ejemplo tests referencian assays existentes).
- Crear pruebas de integracion usando base de datos temporal.

### Fase 4 - UI PySide6 (Semana 3)
- Diseñar ventana principal con boton, indicador de ultima sincronizacion y area de mensajes.
- Integrar pipelines mediante señales y worker thread.
- Manejar estados (en progreso, exito, fallo) y bloquear boton mientras corre la sincronizacion.

### Fase 5 - API FastAPI (Semana 4)
- Crear endpoints GET por entidad con filtros basicos.
- Documentar via OpenAPI y asegurar paginacion en las respuestas.
- Agregar endpoint opcional para disparar sincronizacion controlado por token interno.

### Fase 6 - Cierre y Documentacion (Semana 4)
- Preparar runbook operativa (pasos para ejecutar sync, restaurar backups, interpretar logs).
- Configurar alembic y generar migraciones iniciales.
- Ajustar README y este roadmap con cualquier cambio.

## 7. Pruebas y Calidad
- Unitarias: cliente API, transformaciones, manejo de errores.
- Integracion: pipelines completos contra PostgreSQL de prueba (docker compose).
- UI: pruebas manuales guiadas y, si da tiempo, pruebas automáticas con Qt Test.
- API: pytest + httpx AsyncClient para validar respuestas y filtros.

## 8. Operacion y Seguridad
- Variables sensibles fuera del repositorio (usar `.env` gestionado con dotenv o herramientas como direnv).
- Script CLI `scripts/run_sync.py` para permitir sincronizacion sin UI.
- Logs con rotacion diaria e inclusion de `run_id`.
- Backup periodico de la base local antes de grandes cambios.

## 9. Preguntas Abiertas / Proximos Pasos
- Confirmar campos y filtros soportados por cada endpoint QBench.
- Definir tamanos de pagina y limites de tasa reales.
- Decidir que hacer con archivos adjuntos (reports PDF u otros).
- Acordar formato de reporte de resultados de cada sincronizacion (por ejemplo JSON o correo manual).

---
**Checklist inmediato**
1. Obtener o copiar documentacion detallada de los endpoints.
2. Configurar estructura inicial del repositorio y dependencias.
3. Disenar esquema SQL inicial para customers y tablas de control, validar con un primer sync.

## Notas de implementacion (2025-10-13)
- Configuracion centralizada (`src/downloader_qbench_data/config.py`) para cargar variables de entorno y construir la URL de PostgreSQL.
- Modelos SQLAlchemy creados (`Customer`, `SyncCheckpoint`) con helper de sesiones que inicializa el esquema automaticamente.
- Pipeline `sync_customers` implementado (full + incremental) con checkpoints, manejo de errores y almacenamiento del JSON completo en `raw_payload`.
- Script CLI `scripts/run_sync_customers.py` permite ejecutar la sincronizacion (`python scripts/run_sync_customers.py --full` para refresco completo).
- Prueba unitaria agregada (`tests/test_customer_ingestion.py`) para validar el parseo de `date_created`.
- Modelo `Order` y pipeline `sync_orders` agregados con soporte incremental, validacion contra clientes locales y checkpoint dedicado.
- Script CLI `scripts/run_sync_orders.py` con barra de progreso para sincronizar ordenes.
- Utilidades compartidas de parseo de fechas y conversion numerica (`ingestion/utils.py`) con pruebas basicas.
- Pipeline `sync_batches` implementado con arrays de IDs, checkpoint dedicado y script CLI (`scripts/run_sync_batches.py`) con opcion para incluir worksheet bruto.
- Pipeline `sync_samples` implementado con validacion de `order_id`, conversion de batches y almacenamiento de metadata de tests.
- Pipeline `sync_tests` implementado con validacion de `sample_id`, worksheet raw y enriquecimiento opcional por test individual.
- Orquestador secuencial (`ingestion/pipeline.py`) que ejecuta customers -> orders -> samples -> batches -> tests reutilizando checkpoints y expuesto via `scripts/run_sync_all.py`.
- API FastAPI inicial (`src/downloader_qbench_data/api`) con endpoints de metricas/entidades, script `scripts/run_api.py` y pruebas usando `fastapi.testclient`.
- Dashboard PySide6 inicial (QtCharts, cards y scroll) que consume la API de metricas recientemente agregada.

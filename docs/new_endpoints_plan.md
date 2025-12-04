# Plan Nuevos Endpoints – QBench Data Downloader

## Objetivo
Diseñar endpoints que expongan métricas clave de clientes, órdenes, muestras, batches y tests a partir de la base de datos PostgreSQL, facilitando análisis operativos y comerciales.

---

## ESTRUCTURA DE LA BASE DE DATOS POSTGRESQL
customers
id, name, date_created, raw_payload(json con la data completa)
orders
id, custom_formatted_id, customer_account_id, date_created, date_completed, date_order_reported, date_received, sample_count(int), test_count(int), state(CREATED, REPORTED, COMPLETED, ON HOLD), raw_payload
samples
id, sample_name, custom_formatted_id, order_id, has_report(bool), batch_ids[], completed_date, date_created, start_date, matrix_type(Concentrate, Sugary CIP-edible, Cured Flower/Kief, LDB, CIP-edible, Infused PreRoll, Uncured Plant Material, Solventless Concentrate), state(COMPLETED, NOT REPORTABLE, IN PROGRESS, DISCONTINUED), test_count(int), sample_weight(numeric), raw_payload. 
batches
is, assay_id, display_name, date_created, date_prepared, last_updated, samples_ids[], test_ids[], raw_payload
tests
id, sample_id, batch_ids[], date_created, state(CANCELLED, REPORTED, CLIENT CANCELLED, NOT REPORTABLE, IN PROGRESS, NOT STARTED, ON HOLD)



## 1. Endpoints por Clientes
- `GET /analytics/customers/summary`
  - Devuelve órdenes totales, muestras totales, tests totales, lead time promedio (creación → completado/reportado) y distribución de estados de orden por cliente.
- `GET /analytics/customers/trends`
  - Evolución mensual de órdenes y altas de clientes; identifica cuentas en crecimiento o caída.
- `GET /analytics/customers/alerts`
  - Lista clientes con porcentaje elevado de órdenes en `ON HOLD` o vencidas según SLA.

**Consideraciones**
- Parámetros de filtro: rango de fechas, porcentaje mínimo para alertas.
- Respuestas agregadas para dashboards, no por registro individual.

---

## 2. Endpoints para Órdenes
- `GET /analytics/orders/throughput`
  - Lead time promedio y mediana desde `date_received`/`date_created` hasta `date_completed` por cliente o global.
- `GET /analytics/orders/funnel`
  - Conteo de órdenes por estado (`CREATED`, `ON HOLD`, `COMPLETED`, `REPORTED`, etc.); ayuda a detectar cuellos.
- `GET /analytics/orders/composition`
  - Relación promedio `sample_count` vs `test_count` por tipo de orden o cliente.
- `GET /analytics/orders/overdue`
  - Detalle de ordenes vencidas (>= 30 dias, estado != `REPORTED`) con KPIs, ranking y heatmap.

**Consideraciones**
- Permitir filtros por cliente, fecha, estado.
- Optimizar consultas con índices en columnas de fecha y estado.

---

## 3. Endpoints para Muestras
- `GET /analytics/samples/matrix-distribution`
  - Distribución de `matrix_type` global y por cliente; resaltar cambios recientes.
- `GET /analytics/samples/cycle-time`
  - Tiempo promedio de ciclo (`date_created` → `completed_date`) segmentado por `matrix_type` y cliente.
- `GET /analytics/samples/report-status`
  - Porcentaje de muestras con `has_report = true`; identificar pendientes.

**Consideraciones**
- Precalcular agregados por `matrix_type` y mes (materialized view).
- Opcional: parámetro `include_tests=true` para retornar `test_count` y estados asociados.

---

## 4. Endpoints para Batches
- `GET /analytics/batches/workload`
  - Tamaño promedio de batch (número de `sample_ids`, `test_ids`) y top batches con mayor carga.
- `GET /analytics/batches/assay-usage`
  - Frecuencia de `assay_id`/`display_name` por cliente; detecta ensayos críticos.
- `GET /analytics/batches/staleness`
  - Diferencia `date_created` vs `last_updated`; alerta lotes estancados.

**Consideraciones**
- Rangos de fechas y filtros por cliente.
- Campos calculados derivados de `raw_payload` si incluye metadatos adicionales.

---

## 5. Endpoints para Tests
- `GET /analytics/tests/state-distribution`
  - Conteo de tests por estado; identificar acumulación en `ON HOLD`, `NOT REPORTABLE`, etc.
- `GET /analytics/tests/turnaround`
  - Tiempo promedio desde `date_created` hasta estado final por tipo de matriz o cliente (requiere timestamp final; usar `last_updated` del batch o campos en `raw_payload`).
- `GET /analytics/tests/batch-impact`
  - Número de tests asociados por batch con detalles de estado; priorización de lotes críticos.

**Consideraciones**
- Incluir filtros de fecha, cliente y `matrix_type`.
- Garantizar índices en `state`, `date_created`.

---

## 6. Endpoints Combinados / SLA
- `GET /analytics/kpis/conversion`
  - Pipeline: órdenes → muestras → tests → reportes. Métricas de conversión por cliente y matriz.
- `GET /analytics/kpis/workload-forecast`
  - Identificación de picos de trabajo comparando creaciones recientes vs. completadas.
- `GET /analytics/kpis/quality`
  - % de tests cancelados o no reportables por cliente/matriz.

**Consideraciones**
- Respuestas compactas listas para dashboards.
- Posible cálculo vía procesos ETL nocturnos + exposición de vistas.

---

## 7. Recomendaciones Técnicas
- Crear vistas/materialized views para aggregates frecuentes (p.ej. `mv_customer_metrics`, `mv_matrix_monthly`).
- Autenticación/Autorización: asegurar que endpoints sensibles requieran roles adecuados.
- Documentar parámetros y ejemplos en OpenAPI/Swagger.
- Implementar caching (ETag/last-modified) para consultas pesadas.
- Incluir pruebas SQL y de integración (fixtures con datos sintéticos representativos).

---

## 8. Próximos Pasos
1. Validar KPIs prioritarios con stakeholders (operaciones, ventas, calidad).
2. Diseñar esquema de vistas/materialized views y programar refrescos.
3. Implementar endpoints prioritarios (clientes y órdenes) con pruebas.
4. Iterar con dashboards/reportes basados en los endpoints.




Nuevas Pestañas

Operational Efficiency: indicadores longitudinales de throughput y tiempos de ciclo para órdenes y muestras; usa GET /analytics/orders/throughput, GET /analytics/samples/cycle-time, GET /analytics/orders/funnel.
Quality & SLA Monitor: foco en estados críticos, alertas y salud del pipeline; aprovecha GET /analytics/customers/alerts, GET /analytics/tests/state-distribution, GET /analytics/kpis/quality.
(Opcional) Product Mix Insights: explora matrix_type, uso de assays y carga por batch; respáldalo con GET /analytics/samples/matrix-distribution, GET /analytics/batches/assay-usage, GET /analytics/batches/workload.
Presentación Por Pestaña

Operational Efficiency: tarjetas KPI (lead time medio, órdenes completadas), línea de tendencia diaria/semana de TAT, gráfico de embudo (created→reported), tabla de órdenes más lentas.
Quality & SLA Monitor: heatmap de estados (ON HOLD, NOT REPORTABLE) por cliente vs tiempo, barra apilada de tests por estado, lista de alertas con umbral configurable.
  - ✅ Implementado en la API local (`/analytics/customers/alerts`, `/analytics/tests/state-distribution`, `/analytics/kpis/quality`) y expuesto en la nueva pestaña del dashboard.
Product Mix Insights: gráfico stacked bar compartiendo volumen por matrix_type, mapa de calor de assay_id por cliente, tabla de top batches por carga de tests/muestras.
Endpoints a Desarrollar

/analytics/orders/throughput, /analytics/orders/funnel, /analytics/samples/cycle-time.
/analytics/customers/alerts, /analytics/tests/state-distribution, /analytics/kpis/quality.
/analytics/samples/matrix-distribution, /analytics/batches/assay-usage, /analytics/batches/workload.

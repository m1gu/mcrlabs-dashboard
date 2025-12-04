# Metrics Dashboard Data Catalog

## Overview Filters Header
- **UI elements**: `From` and `To` date pickers, `Timeframe` dropdown (`daily` \| `weekly`), and `Refresh` button.
- **Endpoint contracts**: Every refresh triggers all overview requests listed below with shared query params `date_from` (ISO-8601 start), `date_to` (ISO-8601 end), optional `customer_id`, `order_id`, `state`, and `sla_hours` (default 48) when supported by the endpoint.
- **Backend filters**: `Sample.date_created`, `Test.date_created`, `Customer.date_created`, and `Test.report_completed_date` are bounded using `_daterange_conditions`, which treats midnight `date_to` values as inclusive by shifting them +1 day.
- **Additional logic**: The `Timeframe` selection currently influences only `/metrics/tests/tat-daily` (7-day moving average for daily, 14-day for weekly) but is passed through the hook so it can gate other charts.

## KPI Summary Cards
- **Endpoint**: `GET /metrics/summary`.
- **Returned fields**: `kpis.total_samples`, `kpis.total_tests`, `kpis.total_customers`, `kpis.total_reports`, `kpis.average_tat_hours`, plus `last_updated_at`, `range_start`, `range_end`.
- **Database sources**:
  - `Samples`: count of rows in `samples` filtered by `Sample.date_created` and optional `Order.customer_account_id`, `Sample.order_id`, `Sample.state`.
  - `Tests`: count of rows in `tests` filtered by `Test.date_created` with optional joins to `samples` and `orders` for customer/order filters.
  - `Customers`: count of rows in `customers` constrained by `Customer.date_created` and optional `Customer.id`.
  - `Reports`: count of `tests` where `Test.report_completed_date` is not null within the date range.
  - `Average TAT`: computed in `get_tests_tat` as the mean of `(Test.report_completed_date - Test.date_created)` in hours; the UI formats the value into `Xd Yh`.
- **Last update stamp**: Derived from `MAX(Test.fetched_at)` and rendered alongside the selected date range.

## Daily Activity Chart (Samples vs Tests)
- **Endpoint**: `GET /metrics/activity/daily`.
- **Returned fields**: `current[]` array with `{ date, samples, tests }` (ISO date string, daily counts). The `previous` series is only populated when `compare_previous=true`.
- **Database sources**: Grouped counts via `_fetch_daily_counts`, which performs `DATE_TRUNC('day', Sample.date_created)` and `DATE_TRUNC('day', Test.date_created)` with the same optional customer/order filters used for the summary cards.
- **Client processing**: Each point is parsed to a Date object and labeled using `formatDateLabel`; values feed the dual bar chart (blue for samples, green for tests). Empty dates across either series are filled with zero to keep the timeline aligned.
- **Noteworthy parameters**: UI currently requests `compare_previous=false`, so only the `current` series is plotted despite the service supporting period-over-period comparisons.

## New Customers Table
- **Endpoint**: `GET /metrics/customers/new`.
- **Returned fields**: `customers[]` array containing `{ id, name, created_at }`, where `created_at` is an ISO timestamp.
- **Database sources**: Query targets the `customers` table, filtering by `Customer.date_created` using `_daterange_conditions` and ordering by most recent creation date. Limit defaults to 10; the frontend passes `limit=10` explicitly.
- **Client processing**: Each row is parsed to `{ id, name, createdAt: Date }`, and the grid renders the fields directly. No additional sorting occurs beyond the server-provided order.
- **Filter interactions**: Respects `date_from`/`date_to` to bound creation time. Customer, order, and state filters do not apply because new customers are independent of sample/test entities.

## Top Customers by Tests Table
- **Endpoint**: `GET /metrics/customers/top-tests`.
- **Returned fields**: `customers[]` array with `{ id, name, tests }`, where `tests` is the aggregated count per customer.
- **Database sources**: Aggregates the `tests` table, joining to `samples` and `orders` as needed to apply `date_from`, `date_to`, and customer filtering. Counts are grouped by `Order.customer_account_id` and limited to the requested `limit` (UI passes `limit=10`).
- **Client processing**: Response rows are mapped to `{ id, name, tests }` and then sorted descending client-side (`Array.sort`) even though the SQL query already orders by count; this double sort keeps the UI consistent if the API ordering changes.
- **Filter interactions**: Shares the same date range filters as the activity chart. Additional optional filters (`customer_id`, `order_id`, `state`) flow through `_apply_test_filters`, narrowing the aggregation.

## Tests by Label Bar Chart
- **Endpoint**: `GET /metrics/tests/label-distribution`.
- **Returned fields**: `labels[]` array of `{ label, count }` for a predefined set of abbreviations (e.g., `CN`, `MB`, `FFM`, `HO`).
- **Database sources**: Counts originate from the `tests` table, constrained by the selected date range on `Test.date_created` and optional customer/order/state filters. The query restricts labels to the `target_labels` constant and fills missing labels with zero before returning them.
- **Client processing**: UI maps the array to chart datapoints, sorts descending by `count`, and renders a horizontal bar chart with `count` on the X axis. Labels without data still appear due to the zero-fill logic, keeping the taxonomy consistent.
- **Filter interactions**: Honors `date_from`, `date_to`, `customer_id`, `order_id`, and `state`. Because the endpoint filters on `Test.date_created`, timeframe changes only impact which tests fall in range; there is no additional grouping or moving average.

## Daily TAT Trend Chart
- **Endpoint**: `GET /metrics/tests/tat-daily`.
- **Returned fields**: `points[]` with `{ date, average_hours, within_sla, beyond_sla }` and optional `moving_average_hours[]` containing `{ period_start, value }` pairs for the rolling average.
- **Database sources**: Aggregation runs on the `tests` table filtered by `Test.report_completed_date` and restricted to rows where that column is not null. The service computes `tat_expr = (Test.report_completed_date - Test.date_created)` in hours, groups by `DATE_TRUNC('day', Test.report_completed_date)`, and sums SLA categories using CASE expressions against `sla_hours` (default 48).
- **Client processing**: Each point is mapped to `{ label, withinSla, beyondSla, averageHours, movingAverageHours }`, where `label` is derived via `formatDateLabel`. Recharts renders stacked areas for counts (within vs. beyond SLA), a solid line for daily average hours, a dashed line for the rolling average (7-day when timeframe=daily, 14-day when timeframe=weekly), and a reference line at 48 hours for the SLA target.
- **Filter interactions**: Supports `date_from`, `date_to`, `customer_id`, `order_id`, `state`, `sla_hours`, and `moving_average_window`. The frontend passes only the date range plus a window tuned by timeframe, so SLA threshold stays at the backend default unless overridden by future UI controls.

## Operational Efficiency Filters Header
- **UI elements**: `From`/`To` date pickers, `Interval` dropdown (`day` \| `week`), and shared `Refresh` button with optimistic re-fetch support.
- **Endpoint contracts**: `fetchOperationalData` fans out to `/analytics/orders/throughput`, `/analytics/samples/cycle-time`, `/analytics/orders/funnel`, and `/analytics/orders/slowest`. Only the first two drive the KPIs and charts shown in the screenshot.
- **Backend filters**: Orders use `_daterange_conditions` on `Order.date_created` and `Order.date_completed`; samples use `_sample_cycle_conditions` on `Sample.completed_date`. Selecting `week` changes the `DATE_TRUNC` granularity in both services.
- **Additional logic**: Interval affects the moving-average window only indirectly (averages are aggregated server-side per period). Customer/order/matrix filters exist at the API level but the current UI does not expose them.

## Operational Lead-Time KPIs
- **Endpoint**: `GET /analytics/orders/throughput` (totals payload).
- **Returned fields**: `totals.orders_completed`, `totals.average_completion_hours`, `totals.median_completion_hours`; each period point also echoes `orders_created`, `orders_completed`, `average_completion_hours`, `median_completion_hours`.
- **Database sources**:
  - `Average/Median Lead Time`: computed as the AVG and P50 of `(Order.date_completed - Order.date_created)` in hours for completed orders within the filtered range.
  - `Orders Completed`: count of `Order.date_completed` not null in the same filter window.
  - `Samples Completed`: sourced from `/analytics/samples/cycle-time` totals (`Sample.completed_date` not null).
- **Client processing**: Lead-time hours are formatted via `formatHoursToDuration` (e.g., `12d 22h`), while counts render as plain numbers. The KPI card captions clarify that the metrics describe order completion time.
- **Filter interactions**: Honors `date_from`, `date_to`, `customer_id`. Missing `date_completed` rows are excluded from completion stats; interval choice does not change totals but controls chart series aggregation.

## Order Throughput & Completion Chart
- **Endpoint**: `GET /analytics/orders/throughput`.
- **Returned fields**: `points[]` each supplying `period_start`, `orders_created`, `orders_completed`, `average_completion_hours`, `median_completion_hours`.
- **Database sources**:
  - `Orders created`: grouped count of `Order.date_created`.
  - `Orders completed`: grouped count of `Order.date_completed`.
  - `Average completion (h)`: grouped AVG of `(Order.date_completed - Order.date_created)` in hours.
  - `Median completion (h)`: grouped median via `percentile_cont(0.5)`; currently unused by the UI but available for future overlays.
- **Client processing**: `period_start` is parsed and labeled (`formatDateLabel`) for axis ticks. Recharts renders blue/green bars for created vs completed counts (left Y-axis) and an orange line for `averageCompletionHours` on the right Y-axis. Tooltips surface both counts and hours per interval.
- **Filter interactions**: Supports `date_from`, `date_to`, `interval`, `customer_id`. Aggregation interval is enforced by `DATE_TRUNC(interval, ...)`, yielding day- or week-level buckets aligned with the filter header.

## Sample Cycle Time Chart
- **Endpoint**: `GET /analytics/samples/cycle-time`.
- **Returned fields**: `points[]` with `period_start`, `completed_samples`, `average_cycle_hours`, `median_cycle_hours`, plus totals and `by_matrix_type` (not plotted here).
- **Database sources**: Counts and averages operate on the `samples` table, requiring both `Sample.completed_date` and `Sample.date_created`. Cycle duration equals `(Sample.completed_date - Sample.date_created)` in hours, grouped by `DATE_TRUNC(interval, Sample.completed_date)`.
- **Client processing**: The chart plots teal bars for `samplesCompleted` (left Y-axis) and a red line for `averageCycleHours` (right Y-axis). Median values are available but currently omitted; the UI could add them without changing the API.
- **Filter interactions**: Accepts `date_from`, `date_to`, `interval`, and optional `customer_id`, `order_id`, `matrix_type`, `state`. The current screen only toggles interval and date range, so results aggregate all customers and matrix types unless further filters are added.

## Order Funnel Chart
- **Endpoint**: `GET /analytics/orders/funnel`.
- **Returned fields**: `total_orders` (created count) and `stages[]` array with `{ stage, count }`, where `stage` values are snake-case identifiers (`created`, `received`, `completed`, `reported`, `on_hold`).
- **Database sources**: Each stage counts rows in `orders` filtered by the relevant timestamp column (`Order.date_created`, `Order.date_received`, `Order.date_completed`, `Order.date_order_reported`) using `_daterange_conditions`. The `on_hold` bucket uses the created filter plus `Order.state == 'ON HOLD'`.
- **Client processing**: The UI maps stage codes to title case via `toTitleCase` (e.g., `on_hold` -> `On Hold`) and renders a horizontal bar chart with counts on the X axis. Bars are not re-sorted client-side, so the stage order returned by the service dictates the chart layout.
- **Filter interactions**: Accepts `date_from`, `date_to`, `customer_id`. Date filters drive all stage counts simultaneously; missing timestamps are excluded from their respective buckets.

## Cycle Time by Matrix Table
- **Endpoint**: `GET /analytics/samples/cycle-time` (reuses `by_matrix_type` segment).
- **Returned fields**: `by_matrix_type[]` containing `{ matrix_type, completed_samples, average_cycle_hours }`. Matrix names default to `'Unknown'` when null.
- **Database sources**: Aggregates `samples` filtered by `Sample.completed_date` range and optional customer/order/matrix/state criteria. Average hours are computed from `(Sample.completed_date - Sample.date_created)`.
- **Client processing**: Rows are mapped to `{ matrixType, completedSamples, averageHours }`, sorted descending by `completedSamples`, and rendered in a scrollable table with formatted numbers and durations.
- **Filter interactions**: Shares the same query params as the sample cycle chart; picking a specific matrix or state (if exposed later) would reduce the aggregation set before it reaches the UI.

## Slowest Orders Table
- **Endpoint**: `GET /analytics/orders/slowest`.
- **Returned fields**: `items[]` providing `{ order_id, order_reference, customer_name, state, completion_hours, age_hours }`, along with raw creation/completion timestamps for audit purposes.
- **Database sources**: Operates on the `orders` table constrained by `Order.date_created` and optional `customer_id`/`state`. Completion duration is `(Order.date_completed - Order.date_created)` in hours; age fallback uses `(reference_datetime - Order.date_created)` where `reference_datetime` defaults to `NOW()` or the end of the selected range. Results are ordered by `COALESCE(completion_hours, age_hours)` descending.
- **Client processing**: The UI slices the list to 10 entries (matching the API limit), formats hours into `Xd Yh`, and surfaces a fallback reference label (`order-{id}`) when `custom_formatted_id` is missing. Status pills display the title-cased `state`, or `--` when null.
- **Filter interactions**: Supports `date_from`, `date_to`, `customer_id`, `state`, and `limit` (default 10, capped at 100). Changing the date range affects both completion and age calculations because the reference time clamps to `date_to` when provided.

## Priority Orders Filters Header
- **UI elements**: Read-only range display (last 30 days), numeric inputs for `Minimum days overdue` and `SLA (hours)`, and a `Refresh` button. Interval is fixed to `day` inside `PriorityOrdersTab`.
- **Endpoint contracts**: `fetchPriorityOrders` calls `/analytics/orders/overdue` with `date_from/date_to` (rolling 30-day window), `interval`, `min_days_overdue`, constant `warning_window_days=5`, `sla_hours`, and fixed limits (`top_limit=20`, `client_limit=20`, `warning_limit=10`).
- **Backend filters**: Core conditions use `_daterange_conditions(Order.date_created, date_from, date_to)` plus `Order.state != 'REPORTED'`. Overdue status requires `(reference_time - Order.date_created) >= min_days_overdue * 24h`; SLA breach compares the same open-hours metric against `sla_hours`.
- **Additional logic**: Changing inputs updates component state; `Refresh` either re-fetches with unchanged filters or rebuilds the default rolling window before issuing a new request.

## Priority Overdue KPIs
- **Endpoint**: `GET /analytics/orders/overdue` (`kpis` block).
- **Returned fields**: `total_overdue`, `average_open_hours`, `max_open_hours`, `percent_overdue_vs_active`, `overdue_beyond_sla`, `overdue_within_sla`.
- **Database sources**: Metrics come from the overdue subset of `orders` where `open_hours_expr >= min_days_overdue*24`. Counts and averages are computed directly on `open_hours_expr = (reference_time - Order.date_created)/3600`. `overdue_beyond_sla` simply increments when `open_hours_expr > sla_hours`.
- **Client processing**: `totalOverdue` and `overdueBeyondSla` populate the two KPI cards (with alert styling when SLA is breached). Hours are converted to `Xd Yh` in supporting tooltips; `percentOverdueVsActive` is available for future copy but omitted from the card stack.
- **Filter interactions**: KPIs respond to `min_days_overdue`, `sla_hours`, and date_range. Interval affects only timeline aggregation, not the KPI calculations.

## Most Overdue Orders Table
- **Endpoint**: `GET /analytics/orders/overdue` (`top_orders` array).
- **Returned fields**: `{ order_id, custom_formatted_id, customer_name, state, date_created, open_hours }`.
- **Database sources**: Same overdue conditions as KPIs; rows are sorted by `open_hours` descending so the longest-open orders appear first.
- **Client processing**: Entries map to `{ id, reference, customer, state, createdAt, openHours, slaBreached }`, with SLA flag determined client-side using the provided `sla_hours`. The table shows formatted creation timestamps and open duration along with a yes/no badge for SLA breach.
- **Filter interactions**: Shares `min_days_overdue`, `sla_hours`, and date filters. Adjusting `min_days_overdue` can drop orders below the threshold, shrinking the table.

## Ready to Report Samples Table
- **Endpoint**: `GET /analytics/orders/overdue` (`ready_to_report_samples` array).
- **Returned fields**: `{ sample_id, sample_name, order_custom_id, customer_name, completed_date, tests_ready_count, tests_total_count }`.
- **Database sources**: Derived from `samples` joined to `orders` and `tests`. The service selects samples where every associated test is in a ready state (`COMPLETED` or `NOT REPORTABLE`), the sample was created within the last 30 days, and the parent order is still active (`state not in ('COMPLETED','REPORTED')`).
- **Client processing**: The UI lists sample name, order reference, customer, completion timestamp, and a `tests_ready/tests_total` indicator. Rows are sorted by `Sample.date_created` ascending, mirroring the service query.
- **Filter interactions**: Range anchors to `date_to` (current refresh time) so the lookback window moves with each fetch. `sla_hours` does not impact this table.

## Overdue Heatmap
- **Endpoint**: `GET /analytics/orders/overdue` (`heatmap` array).
- **Returned fields**: `{ customer_name, period_start, overdue_orders }` with intervals aligned to `interval` (`day` or `week`).
- **Database sources**: Counts overdue orders grouped by `Customer` and `DATE_TRUNC(interval, Order.date_created)`. Only overdue rows contribute, so bins with zero overdue orders are absent.
- **Client processing**: Data is normalized into a matrix keyed by period (sorted ascending) and customer (sorted by total overdue descending). Rendered via Nivo heatmap with sequential reds color scale; empty cells default to light shading and tooltips display formatted dates and counts.
- **Filter interactions**: Responds to the same `min_days_overdue`, `sla_hours`, date range, and interval. Extending `min_days_overdue` may empty early periods because fewer orders surpass the threshold.

## Overdue Orders Timeline Chart
- **Endpoint**: `GET /analytics/orders/overdue` (`timeline` array).
- **Returned fields**: `{ period_start, overdue_orders }` aggregated by `DATE_TRUNC(interval, Order.date_created)` for overdue orders.
- **Database sources**: Mirrors the heatmap query but collapses across customers, returning a single count per period.
- **Client processing**: Points are parsed to `{ date, label, overdueOrders }` and plotted as a simple line chart (orange line) against the period axis. Axis labels use `formatDateLabel` to pick human-readable week/day captions.
- **Filter interactions**: Controlled by the same filters as the heatmap. Interval switching would change the spacing of timeline points, though the current UI keeps it at daily granularity.

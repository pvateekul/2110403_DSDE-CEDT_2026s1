# Phase 1: nightly trip batch

## Story and goal

MetroRide starts with a nightly CSV export from its booking system. The operations manager asks for a daily view of demand, completed rides, cancellations, fares, and the time between a request and passenger pickup. There is no driver-app or weather data yet. Call this last measure **passenger pickup wait**; the booking record cannot tell when the driver reached the pickup point.

## Data flow

```mermaid
flowchart LR
    A[Booking system: nightly CSV] --> B[bronze.trips_raw]
    B --> C[silver.trips]
    C --> D[gold.daily_service_performance]
```

## Bronze table and sample files

[`trips_2026-04.csv`](bronze/trips_2026-04.csv) · [`trips_2026-05.csv`](bronze/trips_2026-05.csv)

`bronze.trips_raw` has one received booking row per `trip_id`. The CSV columns stay as source strings. A real bronze table also stores the ingest metadata described in the [case overview](../../README.md). The April and May files contain 132 and 137 trips respectively.

| Column | Bronze CSV type | Meaning |
|---|---|---|
| `trip_id` | text | Booking identifier. |
| `driver_id` | text | Assigned driver. |
| `service_zone` | text | Siam, Asok, Ari, or Silom. |
| `requested_at` | text | Request timestamp. |
| `accepted_at` | text | Driver acceptance timestamp. |
| `picked_up_at` | text, blank if cancelled | Passenger pickup timestamp. |
| `completed_at` | text, blank if cancelled | Ride end timestamp. |
| `cancelled_at` | text, blank if completed | Cancellation timestamp. |
| `status` | text | `completed` or `cancelled`. |
| `fare_thb` | text, blank if cancelled | Charged fare. |

## Silver table

`silver.trips` has one validated row per `trip_id`.

| Columns | Silver types | Rule |
|---|---|---|
| `trip_id`, `driver_id`, `service_zone`, `status` | text, not null | Keep source identifiers and normalized status. |
| `requested_at`, `accepted_at` | timestamp with time zone, not null | Parse `+07:00`; require request before acceptance. |
| `picked_up_at`, `completed_at`, `cancelled_at` | timestamp with time zone, nullable | Enforce the event order for each status. |
| `fare_thb` | decimal(10,2), nullable | Present and nonnegative only for completed trips. |
| `service_date` | date, not null | Date of `requested_at` in Bangkok. |
| `time_slot` | text, not null | `morning` for 08:00–08:59; `evening` for 18:00–18:59. |

## Gold table and indicators

`gold.daily_service_performance` has one row per `service_date` and `time_slot`.

| Column | Type | Calculation from `silver.trips` |
|---|---|---|
| `service_date` | date | Group key. |
| `time_slot` | text | Group key. |
| `requests` | integer | Count all trips. |
| `completed_trips` | integer | Count `status = completed`. |
| `cancelled_trips` | integer | Count `status = cancelled`. |
| `cancellation_rate_pct` | decimal(5,2) | `100 × cancelled_trips / requests`. |
| `gross_fare_thb` | decimal(12,2) | Sum fares for completed trips. |
| `average_passenger_pickup_wait_minutes` | decimal(8,2), nullable | Average `picked_up_at - requested_at` for completed trips, in minutes. |

## Transformations

**Bronze → silver.** Parse timestamps and fare; check required identifiers, zone, status, and unique `trip_id`. For completed trips require `requested_at <= accepted_at <= picked_up_at <= completed_at`, a fare, and no cancellation time. For cancelled trips require `requested_at <= accepted_at <= cancelled_at`, with blank pickup, completion, and fare fields. Reject bad records with a reason while preserving the bronze input. Derive `service_date` and `time_slot` from `requested_at`.

**Silver → gold.** Group by date and slot. Count every valid request, then calculate completed count, cancelled count, rate, fares, and average passenger pickup wait. Round displayed rates and minutes only after aggregation. A replay of the same nightly file must not increase the counts.

**Schema introduced in this phase:** `bronze.trips_raw`, `silver.trips`, and `gold.daily_service_performance`. Phase 2 adds app events and new arrival measures without changing the trip CSV.

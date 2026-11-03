"""Create and check the synthetic bronze CSV fixtures for the ride-hailing case.

Run from any directory:
    python3 case/ride-hailing/generate_sample_data.py
    python3 case/ride-hailing/generate_sample_data.py --check
"""

from __future__ import annotations

import argparse
import csv
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "phases"
PHASE_MONTHS = {
    "phase-1-batch": ((2026, 4), (2026, 5)),
    "phase-2-streaming": ((2026, 6), (2026, 7), (2026, 8)),
    "phase-3-web-scraping": ((2026, 9),),
}
PHASE_TABLES = {
    "phase-1-batch": ("trips",),
    "phase-2-streaming": ("trips", "driver_events"),
    "phase-3-web-scraping": ("trips", "driver_events", "weather"),
}
BKK = timezone(timedelta(hours=7))
ZONES = ("Siam", "Asok", "Ari", "Silom")
WEATHER_URL = "https://www.tmd.go.th/weather/province/bangkok"
FIELDS = {
    "trips": (
        "trip_id", "driver_id", "service_zone", "requested_at", "accepted_at",
        "picked_up_at", "completed_at", "cancelled_at", "status", "fare_thb",
    ),
    "driver_events": (
        "event_id", "trip_id", "driver_id", "event_type", "event_at",
        "latitude", "longitude",
    ),
    "weather": (
        "observed_at", "city", "time_slot", "rain_mm", "source_page",
    ),
}


def stamp(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""


def csv_bytes(rows: list[dict[str, str]], fields: tuple[str, ...]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def make_month(year: int, month: int) -> dict[str, bytes]:
    rows: dict[str, list[dict[str, str]]] = {name: [] for name in FIELDS}
    day = date(year, month, 1)
    trip_number = 0

    while day.month == month:
        for slot, hour in (("morning", 8), ("evening", 18)):
            rainy = (day.timetuple().tm_yday + (4 if slot == "evening" else 0)) % 5 == 0
            rain_mm = 2.0 + (day.day % 6) * 1.5 if rainy else (0.2 if day.day % 4 == 0 else 0.0)
            observed = datetime(day.year, day.month, day.day, hour, tzinfo=BKK)
            rows["weather"].append({
                "observed_at": stamp(observed),
                "city": "Bangkok",
                "time_slot": slot,
                "rain_mm": f"{rain_mm:.1f}",
                "source_page": WEATHER_URL,
            })

            # Two requests per slot, plus a third on rainy slots.
            for position in range(3 if rainy else 2):
                trip_number += 1
                trip_id = f"BKK-{day:%Y%m%d}-{slot[0].upper()}{position + 1}"
                driver_id = f"D{1 + (trip_number % 18):03d}"
                zone_index = (day.day + position + (1 if slot == "evening" else 0)) % len(ZONES)
                requested = observed + timedelta(minutes=position * 17 + 3)
                accepted = requested + timedelta(minutes=1 + trip_number % 3)
                arrival = accepted + timedelta(minutes=3 + trip_number % 5 + (4 if rainy else 0))
                cancelled = (trip_number % (9 if rainy else 19)) == 0
                picked_up = None if cancelled else arrival + timedelta(minutes=1 + trip_number % 3)
                completed = None if cancelled else picked_up + timedelta(minutes=12 + trip_number % 15)
                cancelled_at = accepted + timedelta(minutes=2) if cancelled else None
                fare = "" if cancelled else f"{75 + (12 + trip_number % 15) * 5 + zone_index * 8:.2f}"

                rows["trips"].append({
                    "trip_id": trip_id,
                    "driver_id": driver_id,
                    "service_zone": ZONES[zone_index],
                    "requested_at": stamp(requested),
                    "accepted_at": stamp(accepted),
                    "picked_up_at": stamp(picked_up),
                    "completed_at": stamp(completed),
                    "cancelled_at": stamp(cancelled_at),
                    "status": "cancelled" if cancelled else "completed",
                    "fare_thb": fare,
                })

                lat = 13.72 + zone_index * 0.016 + position * 0.001
                lon = 100.51 + zone_index * 0.014 + position * 0.001
                for suffix, kind, event_time, drift in (
                    ("A", "accepted", accepted, 0.0),
                    ("P", "gps_ping", accepted + timedelta(minutes=1), 0.001),
                    ("C", "cancelled", cancelled_at, 0.0015) if cancelled else
                    ("R", "arrived_at_pickup", arrival, 0.002),
                ):
                    event = {
                        "event_id": f"{trip_id}-{suffix}",
                        "trip_id": trip_id,
                        "driver_id": driver_id,
                        "event_type": kind,
                        "event_at": stamp(event_time),
                        "latitude": f"{lat + drift:.5f}",
                        "longitude": f"{lon + drift:.5f}",
                    }
                    rows["driver_events"].append(event)
                    # A repeated mobile delivery tests deduplication in Silver.
                    if trip_number == 1 and suffix == "P":
                        rows["driver_events"].append(event.copy())

        day += timedelta(days=1)

    month_name = f"{year}-{month:02d}"
    return {
        f"{table}_{month_name}.csv": csv_bytes(table_rows, FIELDS[table])
        for table, table_rows in rows.items()
    }


def managed_csv_paths():
    for phase in PHASE_TABLES:
        for table in FIELDS:
            yield from (ROOT / phase / "bronze").glob(f"{table}_????-??.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check committed CSVs without changing them")
    args = parser.parse_args()
    expected = {}
    for phase, months in PHASE_MONTHS.items():
        for year, month in months:
            monthly = make_month(year, month)
            tables = PHASE_TABLES[phase]
            for table in tables:
                name = f"{table}_{year}-{month:02d}.csv"
                expected[f"{phase}/bronze/{name}"] = monthly[name]
    if args.check:
        missing_or_changed = [name for name, data in expected.items() if not (ROOT / name).is_file() or (ROOT / name).read_bytes() != data]
        extra = [str(path.relative_to(ROOT)) for path in managed_csv_paths() if str(path.relative_to(ROOT)) not in expected]
        if missing_or_changed or extra:
            raise SystemExit(f"Fixture mismatch: missing/changed={missing_or_changed}, extra={extra}")
        print(f"Verified {len(expected)} monthly bronze CSV files")
    else:
        ROOT.mkdir(parents=True, exist_ok=True)
        for path in managed_csv_paths():
            if str(path.relative_to(ROOT)) not in expected:
                path.unlink()
        for name, data in expected.items():
            target = ROOT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        print(f"Wrote {len(expected)} phase-specific monthly bronze CSV files to {ROOT}")


if __name__ == "__main__":
    main()

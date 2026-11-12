"""Ruam Bike: your lakehouse

Fill in q2-q4: q1 is already answered, as an example of how to answer the others. Don't change
the lines marked "DO NOT modify this line": the grader calls these functions by name, with
these arguments. You may add imports and your own helper functions (an `ingest` and a
`transform` to share between q2 and q4, say), and you may write with plain SQL on
`catalog.connection` as well as with the pyducklake API, as long as the tables, the commit
messages and the number of snapshots are right.

How you're graded:
- Each Question is graded on its own, starting from a correct lakehouse: what the official
  solution's earlier Questions leave. A mistake in q2 doesn't cost you points in q3, but on
  your own machine q3 runs after your q2, so fix earlier Questions first.
- Each Question is scored on what it returns and on what it leaves in the lakehouse: the
  tables' schemas and rows, and its snapshots and their commit messages.
- The grader uses other data with the same file names. Hard-coded answers or ids will fail.

Run `uv run python student.py` to rebuild an empty lakehouse next to this file and run
q1 -> q4 on the files in data/.
"""

import shutil
from pathlib import Path

from pyducklake import (
    Catalog,
    DateType,
    DecimalType,
    IntegerType,
    Schema,
    StringType,
    TimestampTZType,
    optional,
    required,
)

SOURCE_COLUMNS = [
    "rental_id",
    "member_id",
    "bike_id",
    "start_station",
    "end_station",
    "started_at",
    "ended_at",
    "status",
    "fare_thb",
]

BRONZE_SCHEMA = Schema.of(
    *(optional(name, StringType()) for name in SOURCE_COLUMNS),
    required("source_file", StringType()),
    required("source_row_number", IntegerType()),
    required("file_sha256", StringType()),
    required("ingested_at", TimestampTZType()),
)

SILVER_SCHEMA = Schema.of(
    required("rental_id", StringType()),
    required("member_id", StringType()),
    required("bike_id", StringType()),
    required("start_station", StringType()),
    optional("end_station", StringType()),
    required("status", StringType()),
    required("started_at", TimestampTZType()),
    optional("ended_at", TimestampTZType()),
    optional("fare_thb", DecimalType(8, 2)),
    required("ride_date", DateType()),
)


def q1(catalog: Catalog):  # DO NOT modify this line
    # Already answered: the namespaces and both tables, in ONE transaction, "q1: create tables".
    with catalog.begin_transaction():
        catalog.set_commit_message("q1: create tables")
        catalog.create_namespace("bronze")
        catalog.create_namespace("silver")
        catalog.create_table(("bronze", "rentals_raw"), BRONZE_SCHEMA)
        catalog.create_table(("silver", "rentals"), SILVER_SCHEMA)
    return {
        namespace: sorted(name for _, name in catalog.list_tables(namespace))
        for namespace in ("bronze", "silver")
    }


def q2(catalog: Catalog, csv_path: str):  # DO NOT modify this line
    # Part A, ingest into bronze:
    # - file guard: skip the whole file if bronze already has a row with its SHA-256;
    # - row guard: drop a row whose rental_id is already in bronze, or earlier in the same file
    #   (keep the first);
    # - append what is left in one transaction, "q2: bronze ingest rentals_2026-06.csv".
    # Part B, transform into silver ("q2: silver transform"): bronze rows whose rental_id isn't
    # in silver yet (NOT EXISTS), trimmed, typed with TRY_CAST, ride_date in Bangkok time,
    # validated by the handout's rules, one per rental_id (QUALIFY).
    # Return {'bronze_appended': int, 'silver_appended': int, 'rejected': int}.
    raise NotImplementedError("q2 isn't answered yet")


def q3(catalog: Catalog):  # DO NOT modify this line
    # Read only: make no snapshot.
    # Return {'silver_rows': int, 'lost_rentals': int,
    #         'revenue_by_station': {station: float, rounded to 2, all 5 Stations},
    #         'rejected_ids': sorted rental_ids in bronze with no silver row}.
    raise NotImplementedError("q3 isn't answered yet")


def q4(  # DO NOT modify this line
    catalog: Catalog, month1_csv: str, month2_csv: str, corrections_csv: str
):
    # Ingest July (month2_csv), then June again (month1_csv: your file guard skips it);
    # transform; apply the Corrections (refares with upsert, voids with delete) in ONE
    # transaction, "q4: silver corrections"; then count silver as it was at the
    # "q2: silver transform" snapshot. See the handout for every key.
    raise NotImplementedError("q4 isn't answered yet")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    data = here / "data"
    lakehouse = here / "lakehouse"
    shutil.rmtree(lakehouse, ignore_errors=True)
    lakehouse.mkdir()
    catalog = Catalog("lake", str(lakehouse / "lake.ducklake"), data_path=str(lakehouse / "data") + "/")
    catalog.set_option("data_inlining_row_limit", "0")
    catalog.connection.execute("SET TimeZone = 'Asia/Bangkok'")
    # Each print below is followed by what it prints on the sample data in data/ when your
    # answer is right. (The grader uses other data, so its values differ.)
    print("q1:", q1(catalog))
    # q1: {'bronze': ['rentals_raw'], 'silver': ['rentals']}
    print("q2:", q2(catalog, str(data / "rentals_2026-06.csv")))
    # q2: {'bronze_appended': 149, 'silver_appended': 141, 'rejected': 8}
    print("q3:", q3(catalog))
    # q3: {'silver_rows': 141, 'lost_rentals': 7,
    #      'revenue_by_station': {'Siam': 600.25, 'Samyan': 1007.25, 'Chamchuri': 778.0,
    #                             'Lumphini': 853.5, 'Silom': 1071.5},
    #      'rejected_ids': ['R0603-017', 'R0605-030', 'R0608-002', 'R0609-011', 'R0609-025',
    #                       'R0611-028', 'R0630-034']}
    print(
        "q4:",
        q4(
            catalog,
            str(data / "rentals_2026-06.csv"),
            str(data / "rentals_2026-07.csv"),
            str(data / "corrections_2026-07.csv"),
        ),
    )
    # q4: {'bronze_appended': 149, 'silver_appended': 141, 'rows_after_q2': 141,
    #      'rows_after_corrections': 279}

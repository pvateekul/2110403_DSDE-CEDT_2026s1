# MetroRide: a ride-hailing lakehouse in three phases

MetroRide is a fictional ride-hailing service in Bangkok. Its operations manager wants to understand trip demand, cancellations, and pickup delays. The case grows one source at a time so students can see why each new source changes the silver and gold tables.

| Phase | New source | Business question | Case notes and CSVs |
|---|---|---|---|
| 1. Batch, April–May 2026 | Nightly booking-system export | How many requests were completed, and how long did passengers wait to be picked up? | [Phase 1](phases/phase-1-batch/README.md) |
| 2. Real time, June–August 2026 | Driver mobile-app events | When did drivers actually reach the pickup point? | [Phase 2](phases/phase-2-streaming/README.md) |
| 3. Web scraping, September 2026 | Public rainfall observations | Do rainy periods coincide with longer driver arrival waits or more cancellations? | [Phase 3](phases/phase-3-web-scraping/README.md) |

Each phase has its own `bronze/` folder with **one CSV per source per assigned month**. Months do not overlap between phases. Load them in order to build a six-month lakehouse; earlier months remain in its tables when the next phase adds a source. The trip, app-event, and rainfall values are **synthetic classroom data**. In particular, the rainfall values are not observations reported by the Thai Meteorological Department. Phase 3 identifies its [Bangkok weather page](https://www.tmd.go.th/weather/province/bangkok) as the model for a production web collector. App events and weather are unavailable for earlier months, so measures that depend on them remain null there.

All timestamps use Bangkok local time with a `+07:00` offset. Money is in Thai baht. Blank CSV cells mean a source value is absent. A bronze ingest should add `source_file`, `source_row_number`, `ingested_at`, and file hash metadata without changing the raw columns.

The [fixture generator](generate_sample_data.py) writes all 11 CSVs. Run `python3 case/ride-hailing/generate_sample_data.py --check` to verify that the saved files match the generator. The phase documents define the table grains, schemas, transformations, and business indicators.

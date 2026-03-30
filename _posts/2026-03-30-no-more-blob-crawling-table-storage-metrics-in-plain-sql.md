---
layout: post
title: "No more blob crawling: table storage metrics in plain SQL"
subtitle: "DBR 18.0 finally lets you check table storage without leaving SQL"
tags: ["databricks", "administration", "unity catalog", "delta lake", "storage analysis", "sql"]
author: Matt Adams
---

A while back I wrote up [a whole process](/2025-04-26-getting-a-handle-on-the-blobs-behind-unity-catalog/) for figuring out how much storage your Unity Catalog managed tables are actually using. It involved the Azure Blob SDK, a Python script you run locally, dumping results to CSV, uploading that into Databricks, then aggregating with PySpark. It worked fine, but it was a lot of steps for what should be a simple question: "how big is this table, really?"

DBR 18.0 added a SQL command that just answers that directly:

```sql
ANALYZE TABLE my_catalog.my_schema.my_table COMPUTE STORAGE METRICS
```

You don't need cloud credentials, SDK, or to generate CSV files.

## What comes back

You get a single row with the storage broken out into categories:

| Metric | What it is |
|--------|------------|
| `total_bytes` | Everything combined (log + active + vacuumable + time travel) |
| `num_total_files` | Total file count across all categories |
| `active_bytes` | Data files the table is actually using right now |
| `num_active_files` | File count for active data |
| `vacuumable_bytes` | Dead weight you can reclaim with `VACUUM` or predictive optimization |
| `num_vacuumable_files` | File count for vacuumable stuff |
| `time_travel_bytes` | Historical versions kept around for time travel and rollbacks |
| `num_time_travel_files` | File count for time travel |

The vacuumable vs. time travel split is the most useful part. You can immediately tell if a table is bloated because nobody's running `VACUUM`, or if it's just carrying a lot of history.

## Example

```sql
ANALYZE TABLE prod_catalog.sales.transactions COMPUTE STORAGE METRICS
```

| total_bytes | active_bytes | vacuumable_bytes | time_travel_bytes |
|-------------|-------------|------------------|-------------------|
| 5,368,709,120 | 4,294,967,296 | 805,306,368 | 268,435,456 |

So 5.37 GB total, 805 MB of that is garbage you could vacuum away. That's about 15% wasted. If you see that number climbing on tables with frequent updates, it's a good sign vacuum isn't running often enough (or at all).

## Looping over a whole schema

It only works on one table at a time, so if you want to scan everything in a schema:

```python
from pyspark.sql import functions as F

catalog_name = "prod_catalog"
schema_name = "sales"

tables = spark.sql(f"""
    SELECT table_name
    FROM {catalog_name}.information_schema.tables
    WHERE table_schema = '{schema_name}'
      AND table_type = 'MANAGED'
""").collect()

results = []
for row in tables:
    table = f"{catalog_name}.{schema_name}.{row.table_name}"
    try:
        metrics = spark.sql(f"ANALYZE TABLE {table} COMPUTE STORAGE METRICS").collect()[0]
        results.append({
            "table": table,
            "total_bytes": metrics.total_bytes,
            "active_bytes": metrics.active_bytes,
            "vacuumable_bytes": metrics.vacuumable_bytes,
            "time_travel_bytes": metrics.time_travel_bytes,
            "num_total_files": metrics.num_total_files,
        })
    except Exception as e:
        print(f"Skipping {table}: {e}")

df = spark.createDataFrame(results)
df.orderBy(F.col("total_bytes").desc()).display()
```

Nothing too fancy. Loop through `information_schema`, run the command on each table, collect results into a DataFrame. Extend it to multiple schemas if you want.

## Keeping a history

The metrics aren't stored anywhere, they're computed fresh each time. If you want to track growth over time, you can use a Spark Declarative Pipeline to land snapshots into a streaming table with SCD Type 2 tracking. That way you get a full history of how each table's storage has changed, with valid-from/valid-to timestamps handled automatically.

Reusing the `df` from the previous section, add a snapshot timestamp and append it to a raw table:

```python
from pyspark.sql import functions as F

df_with_ts = (
    df.withColumnRenamed("table", "table_name")
      .withColumn("snapshot_time", F.current_timestamp())
)

df_with_ts.write.mode("append").saveAsTable("admin_catalog.monitoring.storage_metrics_raw")
```

That raw table is the source for an SDP pipeline that tracks changes with SCD Type 2.

Then a pipeline definition that reads from that source using `APPLY CHANGES INTO` with SCD Type 2. Each time a table's metrics change, the old row gets closed out and a new one opens:

```sql
CREATE OR REFRESH STREAMING TABLE admin_catalog.monitoring.storage_metrics_history;

APPLY CHANGES INTO LIVE.storage_metrics_history
FROM STREAM(admin_catalog.monitoring.storage_metrics_raw)
KEYS (table_name)
SEQUENCE BY snapshot_time
STORED AS SCD TYPE 2;
```

The `KEYS` clause tracks each table by name, and `SEQUENCE BY` uses the snapshot timestamp to order updates. When `total_bytes` or any other column changes for a given table, SCD Type 2 closes the previous row (sets `__END_AT`) and inserts a new current row. If nothing changed, it's a no-op.

Now you can query the history to see what a table's storage looked like at any point:

```sql
SELECT *
FROM admin_catalog.monitoring.storage_metrics_history
WHERE table_name = 'prod_catalog.sales.transactions'
ORDER BY __START_AT DESC;
```

Or find tables where vacuumable bytes have been growing over time:

```sql
SELECT table_name, __START_AT, vacuumable_bytes
FROM admin_catalog.monitoring.storage_metrics_history
WHERE __ISCURRENT = true
  AND vacuumable_bytes > 1073741824  -- > 1 GB
ORDER BY vacuumable_bytes DESC;
```

Schedule the snapshot job to write into the raw table on whatever cadence makes sense (daily, weekly), and the pipeline takes care of the rest.

## Some caveats

- It does a recursive file listing under the hood, so most tables finish in minutes but really large ones (millions of files) can take a while.
- Works on managed tables, external tables, materialized views, and streaming tables. For MVs and streaming tables, `active_bytes` excludes vacuumable and time travel portions.
- These metrics don't show up in `DESCRIBE EXTENDED`. It's a separate command, separate output.
- Requires DBR 18.0+.

## How this compares to the old approach

The [blob-level method](/2025-04-26-getting-a-handle-on-the-blobs-behind-unity-catalog/) still has a place if you need raw file-by-file detail, or if you're on an older runtime, or if you want to analyze storage without spinning up compute. But for the question most people are actually asking, the SQL command is way less friction:

| | Blob SDK approach | `COMPUTE STORAGE METRICS` |
|---|---|---|
| **Runtime** | Any | DBR 18.0+ |
| **Cloud creds** | Yes | No |
| **Granularity** | Individual blob | Table level (active/vacuumable/time travel) |
| **Cloud-specific** | Yes (Azure code shown) | No |
| **Setup** | Python script + SDK + auth | One SQL statement |
| **Reclaimable storage** | You figure it out manually | Built in (`vacuumable_bytes`) |

## References

- [ANALYZE TABLE ... COMPUTE STORAGE METRICS](https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-analyze-compute-storage-metrics.html)
- [VACUUM](https://docs.databricks.com/en/sql/language-manual/delta-vacuum.html)
- [Predictive Optimization](https://docs.databricks.com/en/optimizations/predictive-optimization.html)
- [Unity Catalog Managed Tables](https://docs.databricks.com/en/data-governance/unity-catalog/create-tables.html#managed-tables)
- [Previous post: Getting a Handle on the Blobs Behind Unity Catalog](/2025-04-26-getting-a-handle-on-the-blobs-behind-unity-catalog/)

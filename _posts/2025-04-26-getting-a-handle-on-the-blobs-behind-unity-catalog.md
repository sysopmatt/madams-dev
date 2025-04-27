---
layout: post
title: "Getting a handle on the blobs behind Unity Catalog"
subtitle: "A Python and PySpark approach to analyzing managed table storage in Azure Blob" 
tags: ["databricks", "administration", "unity catalog", "blob storage", "azure", "pyspark", "python", "storage analysis"] 
author: Matt Adams 
---


Often when working with Unity Catalog, especially with managed tables, the underlying blob storage structure can feel a bit opaque. Understanding storage consumption at the blob level is crucial for cost analysis, identifying unexpectedly large tables, tracking storage growth patterns, and debugging storage issues. This guide provides a practical approach using Python and PySpark for Databricks administrators, data engineers, and platform owners who need to gain visibility into their managed table storage footprint on Azure Blob Storage.

**Download Scripts:**

*   [Python Blob Analysis Script (`analyze_uc_blob_sizes.py`)](https://github.com/sysopmatt/madams-dev/blob/main/assets/blog_post_assets/getting-a-handle-on-the-blobs-behind-unity-catalog/analyze_uc_blob_sizes.py)
*   [PySpark Aggregation Notebook Script (`aggregate_blob_sizes_notebook.py`)](https://github.com/sysopmatt/madams-dev/blob/main/assets/blog_post_assets/getting-a-handle-on-the-blobs-behind-unity-catalog/aggregate_blob_sizes_notebook.py)

![Unity Catalog Blob Analysis Workflow](/assets/img/uc-blob-analysis-flow-diagram.png "Workflow: Python Script -> Azure Blob -> CSV -> Databricks Upload -> PySpark Analysis")

Before running the analysis script, ensure you have authenticated with Azure using the Azure CLI. Open your terminal and run:

```bash
az login
```

Follow the prompts to complete the authentication process. The Python script utilizes `DefaultAzureCredential` from the Azure Identity library, which will automatically pick up your logged-in Azure CLI credentials.

Additionally, you'll need to install the necessary Python libraries if you haven't already:

```bash
pip install azure-storage-blob azure-identity pandas
```

## Python Script for Analyzing Blob Sizes

This script connects to your Azure Blob Storage account, iterates through blobs under a specific path (typically where your Unity Catalog managed tables reside), calculates the total size for each logical "subfolder" (representing tables or partitions), and outputs the results to CSV files. It processes blobs in batches to handle potentially large numbers of files efficiently and saves intermediate results to `sorted_subfolders.csv`. The final, sorted list of folders and their sizes is saved to `sorted_subfolders_final.csv`.

**The script includes logic to be restartable.** If it's stopped and rerun, it will load the paths from the intermediate `sorted_subfolders.csv` file and skip processing blobs it has already recorded, effectively resuming where it left off.

**Download Full Script:**

*   [Python Blob Analysis Script (`analyze_uc_blob_sizes.py`)](https://github.com/sysopmatt/madams-dev/blob/main/assets/blog_post_assets/getting-a-handle-on-the-blobs-behind-unity-catalog/analyze_uc_blob_sizes.py)

**Configuration:** You only need to modify the variables in the `USER CONFIGURATION` section at the top of the script:

1.  `ACCOUNT_NAME`: The name of your Azure Blob Storage account where your Unity Catalog metastore is configured. (Find this in the Azure Portal under Storage Accounts).
2.  `CONTAINER_NAME`: The specific container within the storage account used by your metastore. (Find this in the Azure Portal within your storage account's Containers section).
3.  `SCAN_PREFIX`: The starting path within the container to scan. For managed Unity Catalog tables, this is typically `'metastore/<your metastore uuid>/tables/'`. Replace `<your metastore uuid>` with the actual UUID. Adjust this path if you need to scan external table locations or other directories.
4.  `OUTPUT_CSV_INTERMEDIATE` / `OUTPUT_CSV_FINAL`: Names for the intermediate and final output files.
5.  `BATCH_SIZE`: How many blob records to process before writing an intermediate batch to the CSV (adjust based on memory constraints if needed).

**Important Considerations:**

*   **Scope:** The default `SCAN_PREFIX` targets **managed** tables. If you need to analyze external tables, you must change this prefix to match the root path(s) of your external table locations in blob storage.
*   **Performance:** For metastores managing an extremely large number of files (millions or billions), running this Python script locally might take a significant amount of time and memory. Consider running it on a VM with a good network connection to Azure or exploring alternative approaches for very large-scale scenarios.

Below are the key sections of the script. For the full implementation including Azure client initialization, helper functions (`save_batch_to_csv`, `merge_and_sort_data`), and the main execution block with restart logic, please refer to the [downloadable script file](https://github.com/sysopmatt/madams-dev/blob/main/assets/blog_post_assets/getting-a-handle-on-the-blobs-behind-unity-catalog/analyze_uc_blob_sizes.py).

**Script Configuration:**

```python
# ===============================================
# === USER CONFIGURATION ========================
# ===============================================
ACCOUNT_NAME = "<storage account name>"  # Replace with your Azure Storage account name
CONTAINER_NAME = "<storage container>"  # Replace with your container name
# Define the starting path prefix to scan for blobs.
# For managed tables, this is typically 'metastore/<your-metastore-uuid>/tables/'
# Adjust if scanning external tables or different paths.
SCAN_PREFIX = "metastore/<your metastore uuid>/tables/" # Replace <your metastore uuid>
OUTPUT_CSV_INTERMEDIATE = 'sorted_subfolders.csv'
OUTPUT_CSV_FINAL = 'sorted_subfolders_final.csv'
BATCH_SIZE = 10000 # Number of blobs to process before saving intermediate results
# ===============================================
# === END USER CONFIGURATION ====================
# ===============================================
```

**Core Blob Listing Logic (`list_blobs_recursive` function):**

This function iterates through blobs using `container_client.list_blobs` starting at the specified `prefix`. It checks a set of `processed_blobs_set` (loaded from the intermediate file on restart) to skip blobs that have already been recorded. It accumulates new blob information in batches and calls `save_batch_to_csv` periodically.

```python
def list_blobs_recursive(container_client, prefix, processed_blobs_set=set()):
    print(f"Starting scan for prefix: '{prefix}' using list_blobs")
    if processed_blobs_set:
        print(f"Found {len(processed_blobs_set)} previously processed blobs to skip.")

    try:
        blobs_iterator = container_client.list_blobs(name_starts_with=prefix)
    except Exception as e:
        print(f"Error accessing container or prefix '{prefix}'. Please check configuration and permissions. Error: {e}")
        return 0 # Return 0 processed blobs on error

    batch_data = []
    processed_blobs_total = 0
    processed_in_this_run = 0
    skipped_count = 0
    blobs_in_current_batch = 0

    print("Iterating through blobs found...")
    try:
        for blob in blobs_iterator:
            processed_blobs_total += 1 # Count every blob listed
            if blob.name not in processed_blobs_set:
                # Process only blobs not seen before in the intermediate file
                subfolder = blob.name
                # Note: The full script accumulates size in a defaultdict called subfolder_sizes
                # subfolder_sizes[subfolder] += blob.size
                batch_data.append((subfolder, blob.size))
                processed_in_this_run += 1
                blobs_in_current_batch += 1

                if blobs_in_current_batch >= BATCH_SIZE:
                    # Note: The full script calls save_batch_to_csv(batch_data) here
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Processed batch of {len(batch_data)}. Total blobs scanned so far (incl. skipped): {processed_blobs_total}. Added in this run: {processed_in_this_run}")
                    batch_data.clear()
                    blobs_in_current_batch = 0
            else:
                skipped_count += 1
                # Optional: Print skip message periodically to avoid flooding logs
                # if skipped_count % 10000 == 0:
                #     print(f"Skipped {skipped_count} already processed blobs...")


    except Exception as e:
        print(f"An error occurred while listing blobs: {e}")
    finally:
        # Save any remaining blobs in the last batch
        if batch_data:
            # Note: The full script calls save_batch_to_csv(batch_data) here
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Processed final batch of {len(batch_data)}. Total blobs scanned so far (incl. skipped): {processed_blobs_total}. Added in this run: {processed_in_this_run}")

    print(f"Finished scanning prefix '{prefix}'. Total blobs listed by API: {processed_blobs_total}. Blobs added/processed in this run: {processed_in_this_run}. Skipped: {skipped_count}")
    return processed_in_this_run # Return count of blobs processed *in this run*
```

*(The full script also includes `save_batch_to_csv` for writing intermediate results and `merge_and_sort_data` for creating the final sorted output file.)*

## Loading and Analyzing Data in Databricks

Now that you have the `sorted_subfolders_final.csv` file containing the aggregated blob paths and their sizes, let's load it into Databricks for further analysis.

There are several ways to upload data to Databricks, but one of the simplest for a single CSV file is using the UI:

1.  In your Databricks workspace, navigate to the desired volume in the **Data Explorer**.
2.  Select **Upload to this volume**.
    ![Databricks Upload Data Dialog](/assets/img/dbx-upload-dialog.png "Databricks UI: Upload data dialog")
3.  Once uploaded to a volume, find the menu on the file and select **Create table**.
    ![Databricks Create Table Preview](/assets/img/dbx-create-table-preview.png "Databricks UI: Create table preview screen")
4.  Alternatively, click the **+ New** button in the top-left corner, select **Add or upload data**, then **Upload file**.
    ![Databricks Add Data Menu](/assets/img/dbx-add-data-menu.png "Databricks UI: + New -> Add data")
5.  Drag and drop your `sorted_subfolders_final.csv` file or browse to select it.
6.  Follow the prompts to create a new table. Choose the target catalog and schema where you have `CREATE TABLE` permissions. Make sure to note the table name you choose (e.g., `uploaded_blob_sizes`).
7.  Preview the table and ensure the schema inference correctly identifies the `Subfolder` as `STRING`, `Size` as a numeric type (like `BIGINT` or `DOUBLE`), and `Timestamp` as `STRING` or `TIMESTAMP`. Adjust types if necessary.
8.  Click **Create table**.

### Analyzing Table Sizes with PySpark

Once the table is created, you can query it using PySpark to aggregate the storage used by each table. The `Subfolder` column contains the full path, including the metastore UUID and the table's UUID. We can extract the table UUID and group by it to get the total size for each managed table. This allows you to quickly identify the largest managed tables in your metastore by their unique identifier.

**Configuration:** Before running, update the `TABLE_FULL_NAME` variable at the top of the script with the actual catalog, schema, and table name you used when uploading the CSV via the UI.

Run the following PySpark code in a Databricks notebook:

```python
from pyspark.sql import functions as F

# ===============================================
# === USER CONFIGURATION ========================
# ===============================================
# !! Replace with the actual catalog, schema, and table name you used during UI upload !!
TABLE_FULL_NAME = "your_catalog.your_schema.uploaded_blob_sizes"
# ===============================================
# === END USER CONFIGURATION ====================
# ===============================================

# --- Read the table ---
print(f"Reading data from table: {TABLE_FULL_NAME}")
try:
    df = spark.read.table(TABLE_FULL_NAME)
except Exception as e:
    print(f"Error reading table {TABLE_FULL_NAME}. Please check the name and ensure it exists.")
    raise e

# --- Extract Table UUID and Aggregate Size ---
print("Aggregating storage size by table UUID...")
# The Subfolder path looks like: metastore/<metastore_uuid>/tables/<table_uuid>/<optional_partition_dirs>/<filename>
# We split the string by '/' and get the 4th element which should be the table UUID.
df_agg = (
    df.withColumn("path_parts", F.split(F.col("Subfolder"), "/"))
    # Use element_at(4) because F.split creates an array and Spark SQL's array indexing is 1-based.
    .withColumn("table_uuid", F.element_at(F.col("path_parts"), 4))
    # Ensure Size is numeric for summation
    .withColumn("Size", F.col("Size").cast("long"))
    .groupBy("table_uuid")
    .agg(F.sum("Size").alias("total_size_bytes"))
    # Add human-readable sizes
    .withColumn("total_size_gb", F.round(F.col("total_size_bytes") / (1024**3), 2))
    .withColumn("total_size_tb", F.round(F.col("total_size_bytes") / (1024**4), 4))
    .orderBy(F.col("total_size_bytes").desc())
)

# --- Display Results ---
print(f"\nAggregated sizes per table UUID from {TABLE_FULL_NAME}:")
results_to_display = df_agg.select(
    "table_uuid",
    "total_size_bytes",
    "total_size_gb",
    "total_size_tb"
)
results_to_display.show(truncate=False)

# Suggestion: Visualize the results!
print("\nSuggestion: Use the Databricks visualization tools on the 'results_to_display' DataFrame (or the output table) to create a bar chart showing table sizes.")

# Optional: Join with information_schema to get table names
# This helps map the cryptic UUIDs to human-readable table names.
# Note: Requires appropriate privileges on system tables (SELECT on system.information_schema.tables).
# The system catalog must also be enabled and shared with your workspace.
print("\nAttempting to join with information_schema.tables to get table names...")
try:
    # Adjust schema name if your system catalog uses a different one
    tables_info = spark.read.table("system.information_schema.tables")

    # Extract UUID from table_properties['StorageLocation'] which might look like:
    # '.../metastore-uuid/tables/table-uuid'
    # Or sometimes from table_url if available and formatted suitably.
    # Let's try extracting from StorageLocation as it's more standard for managed tables.
    # Note: This regex assumes the UUID is the last part of the path after '/tables/'.
    tables_info = tables_info.withColumn(
        "extracted_uuid",
        F.regexp_extract(F.col("storage_path"), r'/tables/([0-9a-fA-F\-]+)$', 1)
    )
    # Filter out rows where UUID extraction failed (e.g., external tables with different paths)
    tables_info_filtered = tables_info.filter(F.col("extracted_uuid") != "")

    joined_df = df_agg.join(
        tables_info_filtered,
        df_agg["table_uuid"] == tables_info_filtered["extracted_uuid"],
        "left" # Use left join to keep all aggregated sizes, even if name isn't found
    ).select(
        tables_info_filtered["table_catalog"],
        tables_info_filtered["table_schema"],
        tables_info_filtered["table_name"],
        df_agg["table_uuid"],
        df_agg["total_size_bytes"],
        df_agg["total_size_gb"],
        df_agg["total_size_tb"]
    ).orderBy(F.col("total_size_bytes").desc())

    print("\nJoined results with table names (showing top results):")
    joined_df.show(truncate=False)
except Exception as e:
    print(f"\nCould not join with information_schema.tables. This is optional.")
    print(f"  Error: {e}")
    print("  Ensure you have privileges and the system catalog is enabled and shared.")

print("\nAggregation script finished.")
```

This PySpark script reads your uploaded data, extracts the unique identifier for each table from the blob path, sums up the sizes for all blobs belonging to that table, and displays the results sorted by size, including conversions to GB and TB for easier interpretation. The optional section demonstrates how to join this data with `system.information_schema.tables` to map the UUIDs back to actual table names, providing more context to your storage analysis.

# Conclusion

Gaining visibility into the underlying storage of your Unity Catalog managed tables doesn't have to be a black box. By leveraging the Azure SDK in Python to scan blob storage and PySpark in Databricks to analyze the results, you can effectively:

1.  **Quantify Storage:** Run the Python script locally (or on a VM) to list blobs and their sizes within your metastore's container path, outputting to a CSV.
2.  **Load Data:** Upload the resulting CSV easily using the Databricks UI.
3.  **Analyze & Aggregate:** Use PySpark to parse the blob paths, extract table UUIDs, and aggregate storage consumption per table.
4.  **Identify:** Quickly pinpoint the largest tables contributing most significantly to your storage footprint.

This approach provides a solid foundation for understanding and managing your Unity Catalog storage costs and patterns on Azure. Remember to adapt the paths and consider performance implications based on the scale of your environment.

# References

Here are links to the official documentation for the key technologies and libraries used in this post:

*   **Azure Documentation**
    *   [Azure Blob Storage Documentation](https://docs.microsoft.com/en-us/azure/storage/blobs/) - Overview and concepts.
    *   [Azure SDK for Python Documentation](https://docs.microsoft.com/en-us/azure/developer/python/) - Hub for Python SDKs.
    *   [Quickstart: Azure Blob Storage library for Python](https://docs.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python) - Getting started with the `azure-storage-blob` library.
    *   [`BlobServiceClient Class (azure.storage.blob)`](https://azuresdkdocs.blob.core.windows.net/$web/python/azure-storage-blob/12.13.0/azure.storage.blob.html#azure.storage.blob.BlobServiceClient) - API reference for the main client (adjust version if needed).
    *   [`list_blobs Method (azure.storage.blob)`](https://azuresdkdocs.blob.core.windows.net/$web/python/azure-storage-blob/12.13.0/azure.storage.blob.html#azure.storage.blob.ContainerClient.list_blobs) - Details on listing blobs (adjust version if needed).
    *   [`azure-identity` library for Python](https://docs.microsoft.com/en-us/python/api/azure-identity/azure.identity?view=azure-python) - Details on authentication methods.
    *   [`DefaultAzureCredential Class (azure.identity)`](https://docs.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python) - Explanation of the default credential chain.
    *   [Azure Command-Line Interface (CLI) Documentation](https://docs.microsoft.com/en-us/cli/azure/) - Main CLI reference.
    *   [`az storage blob` (Azure CLI Reference)](https://docs.microsoft.com/en-us/cli/azure/storage/blob?view=azure-cli-latest) - Specific commands for blob interaction.
*   **Databricks Documentation**
    *   [Databricks Documentation Portal](https://docs.databricks.com/) - Main entry point.
    *   [Unity Catalog Documentation](https://docs.databricks.com/en/data-governance/unity-catalog/index.html) - Introduction and concepts.
    *   [Managed Tables (Unity Catalog)](https://docs.databricks.com/en/data-governance/unity-catalog/create-tables.html#managed-tables) - Specifics on managed table storage.
    *   [Information Schema (System Tables)](https://docs.databricks.com/en/sql/language-manual/sql-ref-information-schema.html) - Documentation for `system.information_schema`.
    *   [Upload data using the add data UI (Databricks)](https://docs.databricks.com/en/ingestion/add-data/index.html) - Guide for UI uploads.
*   **Apache Spark / PySpark Documentation**
    *   [PySpark API Reference](https://spark.apache.org/docs/latest/api/python/index.html) - Main API docs.
    *   [PySpark SQL Module (`pyspark.sql`)](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql.html) - Details on DataFrame operations.
    *   [PySpark Functions (`pyspark.sql.functions`)](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/functions.html) - Reference for functions like `split`, `element_at`, `sum`.
*   **Pandas Documentation**
    *   [Pandas Documentation](https://pandas.pydata.org/docs/) - Main docs.
    *   [`pandas.read_csv`](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html) - API for reading CSVs.
    *   [`pandas.DataFrame.groupby`](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.groupby.html) - API for grouping data.


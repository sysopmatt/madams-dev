import pandas as pd
from azure.storage.blob import BlobServiceClient, BlobPrefix
from azure.identity import DefaultAzureCredential
from collections import defaultdict
import os
from datetime import datetime

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

# Initialize the BlobServiceClient with AAD authentication
print("Initializing Azure Blob Service Client...")
try:
    credential = DefaultAzureCredential()
    blob_service_client = BlobServiceClient(account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net", credential=credential)
    # Initialize the container client
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
    print("Client initialized successfully.")
except Exception as e:
    print(f"Error initializing Azure client: {e}")
    print("Please ensure Azure CLI is logged in (`az login`) and has permissions to the storage account.")
    exit()

# Dictionary to store the size of each subfolder (full blob path)
subfolder_sizes = defaultdict(int)
count_of_batches_written = 0 # Counter for intermediate saves

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
                subfolder_sizes[subfolder] += blob.size
                batch_data.append((subfolder, blob.size))
                processed_in_this_run += 1
                blobs_in_current_batch += 1

                if blobs_in_current_batch >= BATCH_SIZE:
                    save_batch_to_csv(batch_data)
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
            save_batch_to_csv(batch_data)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Processed final batch of {len(batch_data)}. Total blobs scanned so far (incl. skipped): {processed_blobs_total}. Added in this run: {processed_in_this_run}")

    print(f"Finished scanning prefix '{prefix}'. Total blobs listed by API: {processed_blobs_total}. Blobs added/processed in this run: {processed_in_this_run}. Skipped: {skipped_count}")
    return processed_in_this_run # Return count of blobs processed *in this run*

def save_batch_to_csv(batch_data):
    global count_of_batches_written
    df = pd.DataFrame(batch_data, columns=['Subfolder', 'Size'])
    df['Timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    is_new_file = not os.path.isfile(OUTPUT_CSV_INTERMEDIATE)
    try:
        df.to_csv(OUTPUT_CSV_INTERMEDIATE, mode='a', header=is_new_file, index=False)
        count_of_batches_written += 1
        if is_new_file:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -- Created {OUTPUT_CSV_INTERMEDIATE} and wrote first batch ({len(df)} rows)")
    except Exception as e:
        print(f"Error saving batch to CSV {OUTPUT_CSV_INTERMEDIATE}: {e}")

def merge_and_sort_data():
    print(f"Aggregating and sorting data from {OUTPUT_CSV_INTERMEDIATE}...")

    if not os.path.isfile(OUTPUT_CSV_INTERMEDIATE):
        print(f"Intermediate file {OUTPUT_CSV_INTERMEDIATE} not found. Cannot generate final report. Was the scan successful?")
        return

    try:
        # Read all data written during the scan
        all_data = pd.read_csv(OUTPUT_CSV_INTERMEDIATE)

        # Aggregate the sizes per unique blob path (Subfolder)
        # The intermediate file might contain multiple entries if script was rerun, sum them up.
        aggregated_data = all_data.groupby('Subfolder')['Size'].sum().reset_index()
        aggregated_data['Timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Add final timestamp

        # Sort by size
        sorted_data = aggregated_data.sort_values(by='Size', ascending=False)
        sorted_data.to_csv(OUTPUT_CSV_FINAL, index=False)
        print(f"Final aggregated and sorted data written to {OUTPUT_CSV_FINAL}")
    except Exception as e:
         print(f"Error during final aggregation and sort: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    processed_blobs_set = set()
    if os.path.isfile(OUTPUT_CSV_INTERMEDIATE):
        print(f"Intermediate file '{OUTPUT_CSV_INTERMEDIATE}' found. Loading previously processed blob paths...")
        try:
            # Read only the 'Subfolder' column to save memory
            processed_df = pd.read_csv(OUTPUT_CSV_INTERMEDIATE, usecols=['Subfolder'], dtype={'Subfolder': str})
            processed_blobs_set = set(processed_df['Subfolder'])
            print(f"Loaded {len(processed_blobs_set)} paths from intermediate file.")
        except FileNotFoundError:
            print("Intermediate file mentioned but not found (race condition?). Starting fresh.")
        except pd.errors.EmptyDataError:
             print("Intermediate file is empty. Starting fresh.")
        except KeyError:
             print(f"Intermediate file '{OUTPUT_CSV_INTERMEDIATE}' does not contain 'Subfolder' column. Cannot resume safely. Please check or remove the file. Exiting.")
             exit()
        except Exception as e:
            print(f"Error reading intermediate file '{OUTPUT_CSV_INTERMEDIATE}': {e}. Cannot resume safely. Please check or remove the file. Exiting.")
            exit()

    total_processed_this_run = list_blobs_recursive(container_client, SCAN_PREFIX, processed_blobs_set)

    # Run merge and sort only if the intermediate file exists (either pre-existing or created in this run)
    if os.path.isfile(OUTPUT_CSV_INTERMEDIATE):
        print("Proceeding to final merge and sort step.")
        merge_and_sort_data()
    else:
        print("No blobs were processed and intermediate file was not created. Final report will not be generated.")

    print("Script finished.") 
---
layout: post
title: "From Batch to Streaming: Supercharging Data Freshness on Azure Databricks"
subtitle: Batch processing was all we needed, until it wasn't.
tags: ["user story", "data engineering", "databricks", "delta live tables", "spark"]
author: Matt Adams
---

We traded in our clunky, nightly batch processing for a sleek, real-time streaming data machine on Azure Databricks. By cleverly combining a hybrid approach with some nifty key generation tricks, we supercharged our data freshness and dramatically slashed reprocessing costs.

## Introduction

Transforming legacy Kimball data models—complete with 15 years of history and a sprawling network of data feeds—from batch to streaming requires a delicate touch. We're talking serious planning and meticulous execution.


## Why We Migrated

*   **Empower Real-Time Customer Engagement:** We wanted to provide real-time feedback to our customers through online web portals and partner integrations, enabling proactive outreach and enhanced care.

*   **Eliminate Costly Data Rework:** Inaccurate timestamps were forcing us to perform full data reprocessing with each batch cycle, a costly and inefficient process we were eager to eliminate.

*   **Escape the Nightly Batch Grind:** Our reliance on rigid nightly data processing schedules meant frequent after-hours work resolving data issues. We sought to liberate ourselves (and our sleep schedules!) from this constant "data firefighting."

## Guiding Principals

1. **Preserve Historical Data Integrity:** We were committed to migrating all historical data without alteration. This meant preserving data generated with legacy logic, even if that logic differed from our current standards. We recognized that this older logic was correct in its original context and shouldn't be retroactively changed. (Some of this data stretched back over eight years!)

1. **Embrace the Medallion Architecture:** We adopted the medallion architecture (Bronze, Silver, Gold) as our guiding framework for data organization and quality management throughout the migration.

1. **Streamline with Streaming:** Where feasible, we prioritized streaming data ingestion and processing to achieve near real-time updates and reduce latency.

1. **Maximize Table Reuse:** To minimize disruption and development effort, we aimed to reuse existing, proven tables and data structures whenever possible.


## Interesting Strategy #1: A Hybrid Approach – Streaming Where It Counts

We faced a challenge: massive tables, both in row count *and* column width (some boasting over 100!). It quickly became clear that real-time updates weren't necessary for every single column. Many columns originated from upstream batch processes, making real-time updates redundant.

Furthermore, some columns were derived from extremely complex aggregations. Migrating these to a streaming model would have violated our "Streamline with Streaming" principle (Guiding Principle #3)—basically, it wouldn't have been a good fit.

{% highlight sql linenos %}
CREATE OR REFRESH STREAMING LIVE TABLE batch_customer_events
AS SELECT
  customer_id,
  aggregated_column,
  batch_updated_column,
  insert_timestamp,
  update_timestamp
FROM gold_batch.customer_events AS events; 
{% endhighlight %}

Our solution? A hybrid approach. We excluded these complex/aggregated columns from our streaming tables. Instead, we continued to process them via a daily batch refresh, then integrated them into our final materialized views. This clever workaround actually _reduced_ costs by eliminating the continuous reprocessing of aggregations that only changed daily. Plus, it saved us significant re-engineering time.

The result? We achieved real-time data ingestion _where it truly mattered_, optimizing our resources and focusing our efforts on the most impactful areas.


## Interesting Strategy #2: Deterministic Primary Key Generation – Ditching the Sequential Shuffle

Our old batch pipelines operated in a strict sequence: dimensions first, then facts. This ensured fact tables could always join to dimensions and grab the necessary primary keys. It was a workaround for limited processing power, but with Azure Databricks' near-infinite scalability, we knew we could do better. Why force a square peg into a round hole?

We reimagined our approach. Instead of relying on sequential processing, we implemented a deterministic hashing function. This function takes the natural key of a record and generates a consistent, unique identifier. By applying this function to both dimension and fact tables, we achieved two key wins:

*   **Eliminated pipeline joins:** No more waiting for dimensions to be processed before facts.
*   **Removed inter-table dependencies:** Dimensions and facts could now be processed concurrently.

The result? We unlocked parallel processing of dimensions and facts, significantly accelerating our data pipelines. This allowed us to fully leverage the power of Databricks and move away from the constraints of our old batch system.


## Results and Benefits – Real-Time Wins

*   **Reduced Project Scope, Maximized Impact:** Our hybrid approach dramatically reduced the project's scope. We focused on migrating the core data to streaming pipelines, delivering immediate value without getting bogged down in complex edge-case columns. This saved significant development time and effort.

*   **Embraced the Power of Streaming:** By rethinking our previous batch-centric constraints, we fully embraced the power of streaming, unlocking near real-time data processing capabilities.

*   **Near Real-Time Data Freshness:** We achieved a data freshness of approximately 5 minutes behind our live systems—a massive improvement of 12-24 hours compared to our previous batch processing schedule.

## Conclusion – A Modern Data Foundation

*   **Prioritize Ruthlessly:** Thoroughly analyze requirements to pinpoint the core needs and focus your initial efforts there. This allows for faster delivery of value and avoids getting bogged down in unnecessary complexity.

*   **What's Next? Continued Modernization:** We plan to continue migrating our remaining data models (approximately 150 in total) as new business use cases emerge, further solidifying our modern data foundation.
---
layout: post
title: "Using Deterministic Primary Keys Instead of Identities 🔑"
subtitle: Asyncronous processing while maintaining foreign-key references in Kimball data modeling
tags: ["data engineering", "databricks", "delta live tables", "spark"]
author: Matt Adams
---

Traditional data warehousing often relies on auto-incrementing IDs as primary keys, leading to dependencies that can hinder data freshness, particularly in streaming environments. This article explores an alternative approach: utilizing deterministic primary keys to improve data loading efficiency and achieve faster data insights.


## Background 

The conventional method involves generating a unique identifier for each record using a sequence or auto-incrementing with an identity column as done below:

```sql
CREATE TABLE example_table (
    id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1),
    value STRING
);

-- Inserting data without specifying the id column
INSERT INTO example_table (value) VALUES ('first row');
INSERT INTO example_table (value) VALUES ('second row');
INSERT INTO example_table (value) VALUES ('third row');
```

This approach introduces a dependency: dimension tables must be loaded before their corresponding fact tables, as the fact table's foreign key references the dimension table's primary key. This sequential loading can introduce delays and impact overall data latency.


To overcome this limitation, we can leverage deterministic primary keys. By generating unique keys based on the natural key attributes of the dimension record itself, we decouple the loading order of dimensions and facts.


## Implementing Deterministic Primary Keys

- **Leveraging `xxhash64`**: The Apache Spark xxhash64 function provides a highly efficient and collision-resistant hash function. By applying xxhash64 to the concatenated values of the natural key attributes, we can generate a unique and stable identifier.

- **Handling Multi-Column Keys**: For dimensions with multiple attributes in their natural key, the concat_ws function can be used to concatenate the values while effectively handling null values. For example:

    ```Python
    .withColumn("dim_sale_key", xxhash64(concat_ws(lit('~'), col("receipt_source_key"), col("store_source_key"), col("sale_type")))) 
    ```

    Using a separator (e.g., '~') within concat_ws prevents collisions that might occur when concatenating columns with similar values.

## Benefits of Deterministic Primary Keys

- **Increased Data Freshness**: By decoupling dimension and fact table loading, we significantly reduce data latency.

- **Improved Data Pipelines**: Asynchronous data loading becomes possible, streamlining data ingestion processes.

- **Enhanced Data Agility**: This approach provides greater flexibility in data modeling and pipeline design.


## Results

By embracing deterministic primary keys, data teams can enhance data freshness, improve data pipeline efficiency, and unlock valuable insights more rapidly. This approach represents a significant shift in data modeling practices, enabling organizations to gain a competitive edge in a data-driven world.

_**Note**: This article provides a high-level overview of deterministic primary keys. The specific implementation may vary depending on the data environment and the complexity of the data model._

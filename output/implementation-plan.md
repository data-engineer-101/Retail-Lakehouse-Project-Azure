# Retail Lakehouse & Real-Time Analytics Platform on Azure
## Complete From-Scratch Implementation Guide

> This guide walks through building a complete Azure Data Engineering project from zero.
> It assumes you have an Azure Student Account ($100 credit) and no prior Azure experience.
> Every resource name, path, configuration value, and decision is documented exactly as implemented.

---

## Table of Contents

1. [What You Are Building](#1-what-you-are-building)
2. [Azure Infrastructure Setup](#2-azure-infrastructure-setup)
3. [Storage Layer — ADLS Gen2](#3-storage-layer--adls-gen2)
4. [Processing Layer — Azure Databricks](#4-processing-layer--azure-databricks)
5. [Bronze Ingestion — Batch](#5-bronze-ingestion--batch)
6. [Streaming Setup — Event Hubs](#6-streaming-setup--event-hubs)
7. [Bronze Ingestion — Streaming via Databricks](#7-bronze-ingestion--streaming-via-databricks)
8. [Stream Analytics Job](#8-stream-analytics-job)
9. [Silver Transformation](#9-silver-transformation)
10. [Gold Aggregation](#10-gold-aggregation)
11. [Azure Data Factory — Pipeline Orchestration](#11-azure-data-factory--pipeline-orchestration)
12. [ADLS Lifecycle Rules + Encryption](#12-adls-lifecycle-rules--encryption)
13. [Azure Synapse Analytics](#13-azure-synapse-analytics)
14. [Security — Managed Identity](#14-security--managed-identity)
15. [Final Folder Structure](#15-final-folder-structure)
16. [Resource Summary](#16-resource-summary)
17. [Architecture Decisions & Trade-offs](#17-architecture-decisions--trade-offs)

---

## 1. What You Are Building

### The Problem

A retail chain has disconnected systems — POS terminals, e-commerce, warehouse, IoT sensors — that cannot share data. Reporting is delayed (daily batch jobs only), inventory management is poor (causing stock-outs), and there is no unified customer data for personalisation.

### The Solution — Medallion Lakehouse Architecture

A three-layer data platform where data moves from raw → clean → aggregated:

```
Raw Sources → [Bronze Layer] → [Silver Layer] → [Gold Layer] → Analytics / Dashboards
               (raw, as-is)    (cleaned)         (aggregated)
```

**Batch flow:**
```
Simulated POS Data → ADF Pipeline → ADLS Bronze → Databricks → Silver → Gold → Synapse SQL
```

**Streaming flow:**
```
Stream Generator → Event Hubs → Databricks Structured Streaming → Bronze (Delta)
                             → Stream Analytics (Tumbling Window) → Bronze (raw JSON)
                                                                  → Gold (aggregated JSON)
```

### Technology Stack

| Layer | Service | What it does |
|---|---|---|
| Storage | Azure Data Lake Storage Gen2 | Stores all data in bronze/silver/gold containers |
| Processing | Azure Databricks | Transforms data across layers using PySpark |
| Orchestration | Azure Data Factory | Schedules and monitors daily pipeline runs |
| Streaming Ingest | Azure Event Hubs | Receives live events from the POS generator |
| Stream Processing | Azure Stream Analytics | Applies tumbling window SQL on the live stream |
| Analytics | Azure Synapse Analytics | Lets analysts query Gold data with plain SQL |

---

## 2. Azure Infrastructure Setup

### 2A. Create the Resource Group

A Resource Group is a logical folder that holds all your project's Azure resources together. Think of it as a project directory — you can manage, monitor, and delete everything inside it as a single unit.

1. Go to [portal.azure.com](https://portal.azure.com) and sign in
2. In the top search bar, search **"Resource groups"** → click it
3. Click **"+ Create"**
4. Fill in:

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group name | `rg-retail-lakehouse-prod` |
| Region | Choose the region closest to you (e.g. East US) — **use the same region for all resources in this guide** |

5. Click **"Review + create"** → **"Create"**

> **Important:** Use the same region for every resource you create in this guide. Mixing regions causes network latency and in some cases connectivity failures between services.

---

## 3. Storage Layer — ADLS Gen2

### 3A. Create the Storage Account

Azure Data Lake Storage Gen2 (ADLS Gen2) is the physical home for all lakehouse data. Unlike regular Blob Storage, ADLS Gen2 supports hierarchical namespaces — true folder structure that Databricks and Synapse treat as first-class citizens.

1. In the Azure Portal search bar, type **"Storage accounts"** → click it
2. Click **"+ Create"**
3. Fill in the **Basics** tab:

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group | `rg-retail-lakehouse-prod` |
| Storage account name | `stretaildatalake122` |
| Region | Same region as your Resource Group |
| Performance | Standard |
| Redundancy | Locally-redundant storage (LRS) — cheapest, fine for dev |

4. Click the **"Advanced"** tab:
   - Under **"Data Lake Storage Gen2"**, check **"Enable hierarchical namespace"** → set to **Enabled**
   - This is the critical setting that makes it ADLS Gen2 instead of plain Blob Storage

5. Leave all other tabs as defaults
6. Click **"Review + create"** → **"Create"**
7. Wait ~1 minute → click **"Go to resource"**

### 3B. Create the Three Containers

Containers are the top-level folders in your storage account. You need three — one per Medallion layer.

1. In `stretaildatalake122`, look at the left sidebar → click **"Containers"** (under Data storage)
2. Click **"+ Container"** → Name: `bronze` → Access level: Private → **"Create"**
3. Click **"+ Container"** → Name: `silver` → Access level: Private → **"Create"**
4. Click **"+ Container"** → Name: `gold` → Access level: Private → **"Create"**

### 3C. Create the Folder Structure

Your containers are empty. Create the folder hierarchy that the lakehouse expects.

1. In the left sidebar → click **"Storage browser"**
2. Click **bronze** container

**Inside bronze — create these folders in sequence:**
- Click **"Add Directory"** → type `sales` → OK
- Click into `sales` → **"Add Directory"** → type `year=2026` → OK
- Click into `year=2026` → **"Add Directory"** → type `month=04` → OK

> **Why `year=YYYY/month=MM` naming?** This is Hive-style partitioning. Databricks and Synapse automatically recognise this pattern. When querying `WHERE month = 04`, the engine skips all other month folders entirely — critical for performance on large datasets.

3. Go back to the container list → click **silver** container
   - **"Add Directory"** → `sales_clean` → OK

4. Go back → click **gold** container
   - **"Add Directory"** → `sales_summary` → OK

**Final folder structure at this point:**
```
stretaildatalake122/
├── bronze/
│   └── sales/
│       └── year=2026/
│           └── month=04/     ← empty, data lands here in Step 5
├── silver/
│   └── sales_clean/          ← empty
└── gold/
    └── sales_summary/        ← empty
```

### 3D. Copy the Storage Account Key

You need this key to connect Databricks to ADLS. Think of it as the master password for your storage account.

1. In `stretaildatalake122` → left sidebar → under **"Security + networking"** → click **"Access keys"**
2. Click **"Show"** next to key1
3. Copy the **Key** value — it is a long base64 string
4. Keep it somewhere safe (Notepad, etc.) — you will use it in every Databricks notebook

> **Never commit this key to Git or share it publicly.** It gives full read/write access to your entire storage account.

---

## 4. Processing Layer — Azure Databricks

### 4A. Create the Databricks Workspace

1. In the Azure Portal search bar → **"Azure Databricks"** → **"+ Create"**
2. Fill in:

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group | `rg-retail-lakehouse-prod` |
| Workspace name | `adb-retail-analytics` |
| Region | Same region as everything else |
| Pricing tier | Standard |

3. Click **"Review + create"** → **"Create"**
4. Wait ~3 minutes → **"Go to resource"** → click **"Launch Workspace"**
   - This opens the Databricks UI in a new browser tab — bookmark it

### 4B. Create the Cluster

A cluster is the compute engine that runs your notebooks. You need to start one before running any code.

1. In the Databricks left sidebar → click **"Compute"**
2. Click **"+ Create compute"**
3. Fill in:

| Field | Value |
|---|---|
| Cluster name | `Retail_Analysis_Engine` |
| Cluster mode | Single node |
| Databricks runtime | Latest LTS (e.g. 14.x LTS) |
| Node type | Standard_DS3_v2 |
| Terminate after | 30 minutes of inactivity |

4. Click **"Create compute"**
5. Wait ~3–5 minutes for the cluster to show a green dot (Running state)

> **Why Single Node?** Sufficient for development. Production would use auto-scaling multi-node job clusters. The 30-minute auto-terminate setting is critical — it shuts the cluster down when idle to protect your credit budget.

### 4C. Understand the ADLS Connection Method

Newer Databricks workspaces disable DBFS mounts. Instead, use `spark.conf.set` to register the storage key in the active Spark session. This is the pattern used in every notebook:

```python
STORAGE_ACCOUNT = "stretaildatalake122"
STORAGE_KEY     = "YOUR_KEY1_HERE"   # the key you copied in step 3D

spark.conf.set(
    f"fs.azure.account.key.{STORAGE_ACCOUNT}.blob.core.windows.net",
    STORAGE_KEY
)

def adls_path(container, subfolder=""):
    base = f"wasbs://{container}@{STORAGE_ACCOUNT}.blob.core.windows.net"
    return f"{base}/{subfolder}" if subfolder else base
```

> **Why `spark.conf.set` instead of mounts?** `dbutils.fs.mount` raises `FeatureDisabledException: DBFS mounts are not available on this workspace` on newer Databricks workspaces. `spark.conf.set` is session-scoped — it is set in every notebook's config cell and re-applied whenever the cluster restarts.

### 4D. Create and Test the Connection Notebook

1. Databricks left sidebar → **"New"** → **"Notebook"**
2. Name: `00_Mount_ADLS`, Language: Python, Cluster: `Retail_Analysis_Engine`
3. In the first cell:

```python
STORAGE_ACCOUNT = "stretaildatalake122"
STORAGE_KEY     = "YOUR_KEY1_HERE"

spark.conf.set(
    f"fs.azure.account.key.{STORAGE_ACCOUNT}.blob.core.windows.net",
    STORAGE_KEY
)

def adls_path(container, subfolder=""):
    base = f"wasbs://{container}@{STORAGE_ACCOUNT}.blob.core.windows.net"
    return f"{base}/{subfolder}" if subfolder else base

print("✅ Config ready")
```

4. Press **Shift+Enter** to run → should print `✅ Config ready`
5. Add a new cell and run:

```python
for container in ["bronze", "silver", "gold"]:
    print(f"\n── {container} ──")
    display(dbutils.fs.ls(adls_path(container)))
```

You should see the folders you created in step 3C listed under each container.

---

## 5. Bronze Ingestion — Batch

### 5A. What Bronze Ingestion Does

This notebook simulates a POS system sending retail orders. In a real project, Azure Data Factory would copy data from a POS database into Bronze. For this project, we generate realistic synthetic data with the same schema as the stream generator.

### 5B. Create the Notebook

1. Databricks → **"New"** → **"Notebook"**
2. Name: `01_Bronze_Ingestion`, Language: Python, Cluster: `Retail_Analysis_Engine`

### 5C. Cell 1 — Configuration

```python
# ── Works both when run manually AND when triggered by ADF ─────
try:
    STORAGE_ACCOUNT = dbutils.widgets.get("storage_account")
    print(f"✅ Running via ADF — storage account: {STORAGE_ACCOUNT}")
except Exception:
    STORAGE_ACCOUNT = "stretaildatalake122"
    print(f"✅ Running manually — storage account: {STORAGE_ACCOUNT}")

STORAGE_KEY = "YOUR_KEY1_HERE"

spark.conf.set(
    f"fs.azure.account.key.{STORAGE_ACCOUNT}.blob.core.windows.net",
    STORAGE_KEY
)

def adls_path(container, subfolder=""):
    base = f"wasbs://{container}@{STORAGE_ACCOUNT}.blob.core.windows.net"
    return f"{base}/{subfolder}" if subfolder else base

print(f"✅ Config ready")
```

> **Why the try/except?** When ADF triggers this notebook it passes `storage_account` as a widget parameter. When you run it manually in Databricks, the widget doesn't exist. This pattern handles both cases gracefully and prints which mode is active — helpful for debugging ADF failures.

### 5D. Cell 2 — Generate Simulated Data

```python
from pyspark.sql import Row
from datetime import datetime, timedelta
import random

random.seed(42)  # makes results reproducible on every run

products        = ["Laptop", "Mobile", "Tablet", "Headphones", "TV"]
cities          = ["Bangalore", "Delhi", "Mumbai", "Chennai", "Hyderabad"]
payment_methods = ["UPI", "Credit Card", "Debit Card"]

def make_order(i):
    price    = random.randint(1000, 50000)
    quantity = random.randint(1, 3)
    event_time = datetime(2026, 4, 1) + timedelta(hours=i)
    return Row(
        order_id       = f"O{i:04d}",
        product        = random.choice(products),
        price          = price,
        quantity       = quantity,
        total_amount   = price * quantity,
        city           = random.choice(cities),
        payment_method = random.choice(payment_methods),
        event_time     = event_time.isoformat()
    )

raw_data  = [make_order(i) for i in range(1, 101)]
df_bronze = spark.createDataFrame(raw_data)

print(f"✅ Generated {df_bronze.count()} rows")
df_bronze.printSchema()
```

### 5E. Cell 3 — Preview

```python
display(df_bronze.limit(10))
```

Always preview before writing — confirm column names, data types, and that values look sensible.

### 5F. Cell 4 — Write to Bronze as Delta

```python
BRONZE_PATH = adls_path("bronze", "sales/year=2026/month=04/")

(
    df_bronze
    .write
    .format("delta")      # Delta = Parquet files + _delta_log/ transaction log
    .mode("overwrite")    # safe to re-run
    .save(BRONZE_PATH)
)

print(f"✅ Written to: {BRONZE_PATH}")
```

> **Why Delta format?** Delta adds a `_delta_log/` folder containing a transaction log on top of Parquet files. This gives you ACID transactions (no partial writes), schema enforcement, time travel (query data as of any past point), and automatic file compaction — none of which plain Parquet or CSV can offer.

### 5G. Cell 5 — Verify

```python
df_verify = spark.read.format("delta").load(BRONZE_PATH)
print(f"Row count: {df_verify.count()}")
display(dbutils.fs.ls(BRONZE_PATH))
```

Expected: 100 rows, Parquet files and a `_delta_log/` folder visible.

---

## 6. Streaming Setup — Event Hubs

### 6A. What Event Hubs Does

Azure Event Hubs is a managed message broker — the cloud equivalent of Apache Kafka. Your stream generator pushes one order event per second into it. Downstream consumers (Databricks, Stream Analytics) read from it independently. If either consumer goes down, events are retained (for 1 day) and can be replayed when it recovers.

### 6B. Create the Event Hubs Namespace

1. Azure Portal → **"+ Create a resource"** → search **"Event Hubs"** → **"Create"**
2. Fill in:

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group | `rg-retail-lakehouse-prod` |
| Namespace name | `evhns-retail-stream` |
| Region | Same region as everything else |
| Pricing tier | **Standard** (not Basic — Basic does not support the Kafka protocol on port 9093 that the generator uses) |
| Throughput units | 1 |

3. Click **"Review + create"** → **"Create"**
4. Wait ~1 minute → **"Go to resource"**

### 6C. Create the Event Hub Topic

1. Inside the `evhns-retail-stream` namespace → click **"+ Event Hub"** at the top
2. Fill in:

| Field | Value |
|---|---|
| Name | `retail-stream` |
| Partition count | 2 |
| Message retention | 1 day |

3. Click **"Create"**

### 6D. Get the Connection String

1. In the namespace left sidebar → click **"Shared access policies"**
2. Click **"RootManageSharedAccessKey"**
3. In the panel that opens on the right, copy **"Connection string–primary key"**

It looks like:
```
Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=xxxxxxxxxxxx
```

4. **Append** `;EntityPath=retail-stream` to the end of this string. The final form used in all scripts:

```
Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=xxxxxxxxxxxx;EntityPath=retail-stream
```

> **Why EntityPath is required:** The namespace-level connection string does not specify which topic to connect to. Without `EntityPath`, the Kafka client cannot determine which Event Hub to subscribe to and raises a `KafkaAdminClient` error.

### 6E. Configure the Stream Generator

The file `retail_stream_generator.py` runs locally on your machine and simulates a live POS terminal. Update the three config lines at the top:

```python
BOOTSTRAP_SERVERS = "evhns-retail-stream.servicebus.windows.net:9093"
TOPIC_NAME        = "retail-stream"
CONNECTION_STRING = "Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=xxxxxxxxxxxx;EntityPath=retail-stream"
```

Install the dependency and run:

```bash
pip install kafka-python
python retail_stream_generator.py
```

You should see one event printed per second:
```
Streaming started... Press Ctrl+C to stop
Sent: {'order_id': 'O1', 'product': 'Laptop', 'price': 23400, ...}
Sent: {'order_id': 'O2', 'product': 'Mobile', 'price': 8700, ...}
```

Leave this terminal running during steps 7 and 8.

---

## 7. Bronze Ingestion — Streaming via Databricks

### 7A. What This Notebook Does

Spark Structured Streaming reads continuously from Event Hubs via the Kafka protocol, parses the JSON events, and writes every 10 seconds to `bronze/sales_stream/` as Delta format. This runs in parallel to the Stream Analytics job — both consume the same Event Hub topic independently.

### 7B. Create the Notebook

1. Databricks → **"New"** → **"Notebook"**
2. Name: `02_Stream_Bronze_Ingest`, Language: Python, Cluster: `Retail_Analysis_Engine`

### 7C. Cell 1 — Configuration

```python
STORAGE_ACCOUNT = "stretaildatalake122"
STORAGE_KEY     = "YOUR_KEY1_HERE"

spark.conf.set(
    f"fs.azure.account.key.{STORAGE_ACCOUNT}.blob.core.windows.net",
    STORAGE_KEY
)

def adls_path(container, subfolder=""):
    base = f"wasbs://{container}@{STORAGE_ACCOUNT}.blob.core.windows.net"
    return f"{base}/{subfolder}" if subfolder else base

EH_NAMESPACE   = "evhns-retail-stream"
EH_TOPIC       = "retail-stream"
EH_CONN_STRING = "YOUR_FULL_CONNECTION_STRING_WITH_ENTITYPATH"

print("✅ Config ready")
```

### 7D. Cell 2 — Create Streaming DataFrame from Event Hubs

```python
# Critical: Databricks uses kafkashaded.org.apache.kafka prefix internally
# Using org.apache.kafka directly causes KafkaAdminClient failures
EH_CONN_STRING_WITH_ENTITY = EH_CONN_STRING  # already has EntityPath appended

EH_SASL = (
    "kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required "
    f'username="$ConnectionString" '
    f'password="{EH_CONN_STRING_WITH_ENTITY}";'
)

KAFKA_OPTIONS = {
    "kafka.bootstrap.servers"  : f"{EH_NAMESPACE}.servicebus.windows.net:9093",
    "kafka.security.protocol"  : "SASL_SSL",
    "kafka.sasl.mechanism"     : "PLAIN",
    "kafka.sasl.jaas.config"   : EH_SASL,
    "subscribe"                : EH_TOPIC,
    "startingOffsets"          : "earliest",  # picks up all available events
    "failOnDataLoss"           : "false",
}

df_stream_raw = (
    spark.readStream
    .format("kafka")
    .options(**KAFKA_OPTIONS)
    .load()
)

print("✅ Streaming DataFrame created")
df_stream_raw.printSchema()
```

> **Why `kafkashaded` prefix?** Databricks bundles its own version of the Kafka client library internally under the `kafkashaded` namespace to avoid version conflicts. If you use `org.apache.kafka` in the JAAS config, Databricks cannot find the class and raises `Failed to create new KafkaAdminClient`.

> **Why `startingOffsets: earliest`?** This picks up all events already sitting in Event Hubs, not just new ones. Useful during testing so you get data immediately without waiting for new events.

### 7E. Cell 3 — Parse JSON and Write to Bronze

```python
from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType
)

event_schema = StructType([
    StructField("order_id",       StringType(),  True),
    StructField("product",        StringType(),  True),
    StructField("price",          LongType(),    True),
    StructField("quantity",       IntegerType(), True),
    StructField("total_amount",   LongType(),    True),
    StructField("city",           StringType(),  True),
    StructField("payment_method", StringType(),  True),
    StructField("event_time",     StringType(),  True),
])

df_stream_parsed = (
    df_stream_raw
    .select(
        from_json(col("value").cast("string"), event_schema).alias("data"),
        current_timestamp().alias("ingested_at")
    )
    .select("data.*", "ingested_at")
)

STREAM_BRONZE_PATH = adls_path("bronze", "sales_stream/")
CHECKPOINT_PATH    = adls_path("bronze", "_checkpoints/sales_stream/")

stream_query = (
    df_stream_parsed
    .writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", CHECKPOINT_PATH)
    .trigger(processingTime="10 seconds")
    .start(STREAM_BRONZE_PATH)
)

print("✅ Stream running — writing to bronze/sales_stream/")
```

> **Why a checkpoint path?** The checkpoint folder (`bronze/_checkpoints/sales_stream/`) stores progress — which Kafka offsets have been successfully processed. If the cluster restarts, the stream resumes from where it left off instead of reprocessing everything from the beginning.

### 7F. Cell 4 — Verify Data Is Landing

Run this in a separate cell while the stream cell above keeps running:

```python
df_live = spark.read.format("delta").load(STREAM_BRONZE_PATH)
print(f"Events landed so far: {df_live.count()}")
display(df_live.orderBy("ingested_at", ascending=False).limit(10))
```

Re-run every 30 seconds — the count should grow by approximately 10 rows each time (10 seconds × 1 event/second).

### 7G. Stop the Stream

When done testing, run in a new cell:

```python
stream_query.stop()
print("✅ Stream stopped cleanly")
```

---

## 8. Stream Analytics Job

### 8A. What Stream Analytics Does

Azure Stream Analytics is a fully managed, always-on stream processing service. It reads from Event Hubs, applies SQL-based tumbling window aggregations, and writes results to ADLS — independently of Databricks. This is the architecturally correct separation: Databricks handles Delta-format batch and streaming, Stream Analytics handles dedicated real-time SQL aggregation.

**Two outputs are created:**
- **Raw passthrough** → `bronze/sales_stream_asa/` (every event, unchanged, JSON format)
- **Aggregated summaries** → `gold/sales_stream_asa/` (1-minute tumbling window, JSON format)

> **Critical format note:** Stream Analytics writes JSON, not Delta. Synapse cannot query ASA output using `FORMAT = 'DELTA'`. ASA JSON output is treated as raw operational logs. All Synapse analytics queries use the Databricks Delta outputs instead.

### 8B. Create the Stream Analytics Job

1. Azure Portal → **"+ Create a resource"** → search **"Stream Analytics job"** → **"Create"**
2. Fill in:

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group | `rg-retail-lakehouse-prod` |
| Name | `asa-retail-stream` |
| Region | Same region as everything else |
| Hosting environment | Cloud |
| Streaming units | 1 |

3. Click **"Review + create"** → **"Create"** → **"Go to resource"**

### 8C. Configure Input — Event Hubs

1. In `asa-retail-stream` left sidebar → **"Inputs"** (under Job topology)
2. Click **"+ Add stream input"** → **"Event Hub"**
3. Fill in:

| Field | Value |
|---|---|
| Input alias | `retail-eh-input` |
| Subscription | Your subscription |
| Event Hub namespace | `evhns-retail-stream` |
| Event Hub name | `retail-stream` |
| Event Hub consumer group | `$Default` |
| Authentication mode | Connection string |
| Event Hub policy name | `RootManageSharedAccessKey` |
| Event serialization format | JSON |
| Encoding | UTF-8 |

4. Click **"Save"**

### 8D. Configure Output 1 — Raw Events to Bronze

1. Left sidebar → **"Outputs"** → **"+ Add"** → **"Azure Data Lake Storage Gen2"**
2. Fill in:

| Field | Value |
|---|---|
| Output alias | `retail-adls-raw-output` |
| Subscription | Your subscription |
| Storage account | `stretaildatalake122` |
| Container | `bronze` |
| Path pattern | `sales_stream_asa/{date}/{time}` |
| Date format | YYYY/MM/DD |
| Time format | HH |
| Authentication mode | Connection string |
| Event serialization format | JSON |
| Format | Line separated |

3. Click **"Save"**

### 8E. Configure Output 2 — Aggregated Events to Gold

1. Left sidebar → **"Outputs"** → **"+ Add"** → **"Azure Data Lake Storage Gen2"**
2. Fill in:

| Field | Value |
|---|---|
| Output alias | `retail-adls-output` |
| Subscription | Your subscription |
| Storage account | `stretaildatalake122` |
| Container | `gold` |
| Path pattern | `sales_stream_asa/{date}/{time}` |
| Date format | YYYY/MM/DD |
| Time format | HH |
| Authentication mode | Connection string |
| Event serialization format | JSON |
| Format | Line separated |

3. Click **"Save"**

> **Why two separate outputs?** A single SELECT INTO both outputs causes a compilation error in ASA. More importantly, separating them enforces the Medallion architecture: raw events belong in Bronze, aggregated summaries belong in Gold. Mixing them in one path blurs the boundary between layers.

### 8F. Write the Query

1. Left sidebar → **"Query"**
2. Replace everything in the editor with:

```sql
-- Aggregated output → GOLD
-- Groups all events in a 1-minute tumbling window by product/city/payment
SELECT
    product,
    city,
    payment_method,
    COUNT(*)            AS order_count,
    SUM(total_amount)   AS total_revenue,
    AVG(total_amount)   AS avg_order_value,
    SUM(quantity)       AS units_sold,
    System.Timestamp()  AS window_end_time
INTO
    [retail-adls-output]
FROM
    [retail-eh-input]
GROUP BY
    product,
    city,
    payment_method,
    TumblingWindow(minute, 1);

-- Raw passthrough → BRONZE
-- Writes every individual event unchanged for full fidelity archive
SELECT
    order_id,
    product,
    price,
    quantity,
    total_amount,
    city,
    payment_method,
    event_time,
    System.Timestamp() AS ingested_at
INTO
    [retail-adls-raw-output]
FROM
    [retail-eh-input];
```

3. Click **"Save query"**

> **What is a Tumbling Window?** A fixed-size, non-overlapping time window. Every 1 minute, Stream Analytics takes all events that arrived in that 60-second window, groups them by product + city + payment_method, and writes one summary row per group. If 60 events arrived in one minute across 5 products, 5 cities, and 3 payment methods, the output is a handful of summary rows — not 60 raw rows.

### 8G. Test the Query with Sample Data

Before starting the job, test it using the built-in sample upload:

1. Click **"Test query"** in the query editor toolbar
2. Click **"Upload sample input"** for `retail-eh-input`
3. Create a file `sample.json` locally with this content:

```json
[
  {"order_id":"O0001","product":"Laptop","price":23400,"quantity":1,"total_amount":23400,"city":"Bangalore","payment_method":"UPI","event_time":"2026-04-04T10:00:00"},
  {"order_id":"O0002","product":"Mobile","price":8700,"quantity":2,"total_amount":17400,"city":"Delhi","payment_method":"Credit Card","event_time":"2026-04-04T10:00:15"},
  {"order_id":"O0003","product":"Laptop","price":31000,"quantity":1,"total_amount":31000,"city":"Mumbai","payment_method":"UPI","event_time":"2026-04-04T10:00:30"},
  {"order_id":"O0004","product":"TV","price":45000,"quantity":1,"total_amount":45000,"city":"Bangalore","payment_method":"Debit Card","event_time":"2026-04-04T10:00:45"},
  {"order_id":"O0005","product":"Tablet","price":12000,"quantity":3,"total_amount":36000,"city":"Chennai","payment_method":"UPI","event_time":"2026-04-04T10:00:55"}
]
```

4. Upload it → click **"Test query"** → verify aggregated rows appear in the output panel

### 8H. Start the Job

1. Go to the **Overview** page of `asa-retail-stream`
2. Click **"Start"** → Output start time: **"Now"** → **"Start"**
3. Wait ~2 minutes for status to change from **Starting** to **Running** (green indicator)

Make sure your stream generator is running in your terminal. After 2–3 minutes:
- `bronze/sales_stream_asa/2026/04/04/HH/` — JSON files with raw events appear
- `gold/sales_stream_asa/2026/04/04/HH/` — JSON files with 1-minute aggregations appear

### 8I. Verify in Azure Portal

1. In `asa-retail-stream` → left sidebar → **"Metrics"**
2. Add metrics:
   - **Input Events** — should tick up at ~1/second
   - **Output Events** — should show batches every 60 seconds
   - **Runtime Errors** — must be 0

---

## 9. Silver Transformation

### 9A. What Silver Transformation Does

Silver is the trusted layer. It takes all raw Bronze data (batch + stream), applies business validation rules, removes duplicates, fixes data types, and writes a clean dataset partitioned by city. Analysts and business users should only ever consume Silver or Gold — never raw Bronze.

### 9B. Create the Notebook

1. Databricks → **"New"** → **"Notebook"**
2. Name: `03_Silver_Transform`, Language: Python, Cluster: `Retail_Analysis_Engine`

### 9C. Cell 1 — Configuration

```python
try:
    STORAGE_ACCOUNT = dbutils.widgets.get("storage_account")
    print(f"✅ Running via ADF — storage account: {STORAGE_ACCOUNT}")
except Exception:
    STORAGE_ACCOUNT = "stretaildatalake122"
    print(f"✅ Running manually — storage account: {STORAGE_ACCOUNT}")

STORAGE_KEY = "YOUR_KEY1_HERE"

spark.conf.set(
    f"fs.azure.account.key.{STORAGE_ACCOUNT}.blob.core.windows.net",
    STORAGE_KEY
)

def adls_path(container, subfolder=""):
    base = f"wasbs://{container}@{STORAGE_ACCOUNT}.blob.core.windows.net"
    return f"{base}/{subfolder}" if subfolder else base

BRONZE_BATCH_PATH  = adls_path("bronze", "sales/year=2026/month=04/")
BRONZE_STREAM_PATH = adls_path("bronze", "sales_stream/")
SILVER_PATH        = adls_path("silver", "sales_clean/")

print("✅ Config ready")
```

### 9D. Cell 2 — Read Both Bronze Sources and Combine

```python
from pyspark.sql.functions import col, to_timestamp, trim, when, lit

df_batch = (
    spark.read.format("delta")
    .load(BRONZE_BATCH_PATH)
    .withColumn("source", lit("batch"))
)

df_stream = (
    spark.read.format("delta")
    .load(BRONZE_STREAM_PATH)
    .withColumn("source", lit("stream"))
)

df_bronze_all = df_batch.unionByName(df_stream, allowMissingColumns=True)

print(f"Batch rows  : {df_batch.count()}")
print(f"Stream rows : {df_stream.count()}")
print(f"Combined    : {df_bronze_all.count()}")
```

### 9E. Cell 3 — Data Quality Check Before Cleaning

```python
from pyspark.sql.functions import count, when, isnull

print("── Null check per column ──")
null_counts = df_bronze_all.select([
    count(when(isnull(c), c)).alias(c)
    for c in df_bronze_all.columns
])
display(null_counts)

total    = df_bronze_all.count()
distinct = df_bronze_all.select("order_id").distinct().count()
print(f"\nTotal rows     : {total}")
print(f"Distinct orders: {distinct}")
print(f"Duplicates     : {total - distinct}")
```

### 9F. Cell 4 — Apply Cleaning Rules

```python
from pyspark.sql.functions import to_timestamp, trim, col, when

df_silver = (
    df_bronze_all
    .dropDuplicates(["order_id"])                          # 1. Remove duplicates
    .dropna(subset=["order_id", "product",                 # 2. Drop nulls on critical cols
                    "price", "total_amount"])
    .withColumn("event_time",    to_timestamp(col("event_time")))  # 3. Fix types
    .withColumn("price",         col("price").cast("long"))
    .withColumn("quantity",      col("quantity").cast("integer"))
    .withColumn("total_amount",  col("total_amount").cast("long"))
    .withColumn("product",        trim(col("product")))            # 4. Trim whitespace
    .withColumn("city",           trim(col("city")))
    .withColumn("payment_method", trim(col("payment_method")))
    .withColumn("is_high_value",                                   # 5. Business rule flag
        when(col("total_amount") > 40000, True).otherwise(False))
)

print(f"✅ Silver row count after cleaning: {df_silver.count()}")
df_silver.printSchema()
```

### 9G. Cell 5 — Preview Clean Data

```python
display(df_silver.limit(10))
```

Confirm: `event_time` is a timestamp (not string), `is_high_value` column exists, no obvious bad values.

### 9H. Cell 6 — Write to Silver as Delta

```python
(
    df_silver
    .write
    .format("delta")
    .mode("overwrite")
    .partitionBy("city")     # creates city=Bangalore/, city=Delhi/, etc.
    .save(SILVER_PATH)
)

print(f"✅ Silver layer written")

df_check = spark.read.format("delta").load(SILVER_PATH)
print(f"Row count: {df_check.count()}")
display(dbutils.fs.ls(SILVER_PATH))
```

Expected output: ~1297 rows, partition folders `city=Bangalore/`, `city=Chennai/`, `city=Delhi/`, `city=Hyderabad/`, `city=Mumbai/` visible.

---

## 10. Gold Aggregation

### 10A. What Gold Aggregation Does

Gold is the business-consumption layer. Instead of analysts scanning ~1300 raw rows, they query small pre-aggregated summary tables with 3–5 rows each. Three Gold tables are produced: by product, by city, by payment method.

### 10B. Create the Notebook

1. Databricks → **"New"** → **"Notebook"**
2. Name: `04_Gold_Aggregation`, Language: Python, Cluster: `Retail_Analysis_Engine`

### 10C. Cell 1 — Configuration

```python
try:
    STORAGE_ACCOUNT = dbutils.widgets.get("storage_account")
    print(f"✅ Running via ADF — storage account: {STORAGE_ACCOUNT}")
except Exception:
    STORAGE_ACCOUNT = "stretaildatalake122"
    print(f"✅ Running manually — storage account: {STORAGE_ACCOUNT}")

STORAGE_KEY = "YOUR_KEY1_HERE"

spark.conf.set(
    f"fs.azure.account.key.{STORAGE_ACCOUNT}.blob.core.windows.net",
    STORAGE_KEY
)

def adls_path(container, subfolder=""):
    base = f"wasbs://{container}@{STORAGE_ACCOUNT}.blob.core.windows.net"
    return f"{base}/{subfolder}" if subfolder else base

SILVER_PATH = adls_path("silver", "sales_clean/")
GOLD_PATH   = adls_path("gold",   "sales_summary/")

df_silver = spark.read.format("delta").load(SILVER_PATH)
print(f"✅ Silver loaded — {df_silver.count()} rows")
```

### 10D. Cell 2 — Sales by Product

```python
from pyspark.sql.functions import (
    sum as spark_sum, count, avg, max as spark_max, round as spark_round
)

gold_by_product = (
    df_silver
    .groupBy("product")
    .agg(
        count("order_id")                .alias("total_orders"),
        spark_sum("total_amount")         .alias("total_revenue"),
        spark_round(avg("total_amount"),2).alias("avg_order_value"),
        spark_max("total_amount")         .alias("max_order_value"),
        spark_sum("quantity")             .alias("units_sold")
    )
    .orderBy("total_revenue", ascending=False)
)

display(gold_by_product)
```

### 10E. Cell 3 — Sales by City

```python
gold_by_city = (
    df_silver
    .groupBy("city")
    .agg(
        count("order_id")                .alias("total_orders"),
        spark_sum("total_amount")         .alias("total_revenue"),
        spark_round(avg("total_amount"),2).alias("avg_order_value"),
    )
    .orderBy("total_revenue", ascending=False)
)

display(gold_by_city)
```

### 10F. Cell 4 — Sales by Payment Method

```python
gold_by_payment = (
    df_silver
    .groupBy("payment_method")
    .agg(
        count("order_id")         .alias("total_orders"),
        spark_sum("total_amount") .alias("total_revenue"),
        spark_round(
            count("order_id") / df_silver.count() * 100, 1
        )                         .alias("pct_of_orders")
    )
    .orderBy("total_orders", ascending=False)
)

display(gold_by_payment)
```

### 10G. Cell 5 — Write All Three Gold Tables

```python
(gold_by_product
 .write.format("delta").mode("overwrite")
 .save(adls_path("gold", "sales_summary/by_product/")))

(gold_by_city
 .write.format("delta").mode("overwrite")
 .save(adls_path("gold", "sales_summary/by_city/")))

(gold_by_payment
 .write.format("delta").mode("overwrite")
 .save(adls_path("gold", "sales_summary/by_payment/")))

print("✅ Gold layer written")

for folder in ["by_product", "by_city", "by_payment"]:
    path = adls_path("gold", f"sales_summary/{folder}/")
    df_c = spark.read.format("delta").load(path)
    print(f"   {folder}: {df_c.count()} rows")
```

Expected: `by_product: 5 rows`, `by_city: 5 rows`, `by_payment: 3 rows`.

---

## 11. Azure Data Factory — Pipeline Orchestration

### 11A. What ADF Does

Without ADF, you run 3 notebooks manually every day. ADF automates this with a scheduled pipeline that runs Bronze → Silver → Gold in sequence every night at midnight, retries once on failure, and keeps a full monitoring history of every run.

### 11B. Create the ADF Workspace

1. Azure Portal → **"+ Create a resource"** → search **"Data Factory"** → **"Create"**
2. Fill in:

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group | `rg-retail-lakehouse-prod` |
| Name | `adf-retail-lakehouse122` |
| Region | Same region as everything else |
| Version | V2 |

3. Click **"Review + create"** → **"Create"** → **"Go to resource"** → **"Launch Studio"**

### 11C. Create Linked Service — Databricks

A Linked Service is a saved, reusable connection to an external service.

1. ADF Studio left sidebar → **"Manage"** (toolbox icon) → **"Linked services"** → **"+ New"**
2. Search **"Azure Databricks"** → **"Continue"**
3. Fill in:

| Field | Value |
|---|---|
| Name | `ls_databricks_retail` |
| Azure subscription | Your subscription |
| Databricks workspace | `adb-retail-analytics` |
| Select cluster | Existing interactive cluster |
| Existing cluster ID | Select `Retail_Analysis_Engine` from dropdown |
| Authentication | Access token |

4. To get the access token: In Databricks → click your profile icon (top right) → **"Settings"** → **"Developer"** → **"Access tokens"** → **"Generate new token"** → Comment: `adf-connection`, Lifetime: 90 days → **"Generate"** → copy the token immediately (shown only once)
5. Paste the token into the ADF form
6. Click **"Test connection"** → should show **"Connection successful"**
7. Click **"Create"**

### 11D. Create Linked Service — ADLS

1. **"Linked services"** → **"+ New"** → search **"Azure Data Lake Storage Gen2"** → **"Continue"**
2. Fill in:

| Field | Value |
|---|---|
| Name | `ls_adls_retail` |
| Authentication method | Account key |
| Storage account | `stretaildatalake122` |

3. Click **"Test connection"** → **"Connection successful"** → **"Create"**

### 11E. Create the Pipeline

1. ADF Studio left sidebar → **"Author"** (pencil icon)
2. Click **"+"** next to Pipelines → **"New pipeline"**
3. Name: `PL_Retail_Lakehouse_Daily`

### 11F. Add the Three Activities

In the activity panel on the left, expand **"Databricks"** → drag **"Notebook"** onto the canvas three times.

**Activity 1 — ACT_Bronze_Ingestion:**
- Click the activity → **General tab** → Name: `ACT_Bronze_Ingestion`
- Retry: `1`, Retry interval: `30` seconds, Timeout: `0.12:00:00`
- **Azure Databricks tab** → Linked service: `ls_databricks_retail`
- **Settings tab** → Notebook path: Browse to `/01_Bronze_Ingestion`
- **Base parameters** → click **"+ New"** → Name: `storage_account`, Value: `stretaildatalake122`

**Activity 2 — ACT_Silver_Transform:**
- Click the second activity → Name: `ACT_Silver_Transform`
- Same retry settings (Retry: 1, Interval: 30s, Timeout: 12h)
- Databricks linked service: `ls_databricks_retail`
- Notebook: `/03_Silver_Transform`
- Parameters: Name: `storage_account`, Value: `stretaildatalake122`
- **Connect to Activity 1:** Hover over `ACT_Bronze_Ingestion` → drag the green arrow to `ACT_Silver_Transform`

**Activity 3 — ACT_Gold_Aggregation:**
- Name: `ACT_Gold_Aggregation`
- Same retry settings
- Notebook: `/04_Gold_Aggregation`
- Parameters: Name: `storage_account`, Value: `stretaildatalake122`
- **Connect to Activity 2:** Green arrow from `ACT_Silver_Transform` → `ACT_Gold_Aggregation`

Final canvas:
```
[ACT_Bronze_Ingestion] ──▶ [ACT_Silver_Transform] ──▶ [ACT_Gold_Aggregation]
```

4. Click **"Publish all"** → **"Publish"**

### 11G. Run the Pipeline Manually

1. **"Add trigger"** → **"Trigger now"** → **"OK"**
2. Click **"Monitor"** (chart icon on left sidebar)
3. Watch `PL_Retail_Lakehouse_Daily` — all 3 activities should turn green (Succeeded) within 5 minutes

### 11H. Add Daily Schedule Trigger

1. Back in **Author** → open `PL_Retail_Lakehouse_Daily`
2. **"Add trigger"** → **"New/Edit"** → **"+ New"**
3. Fill in:

| Field | Value |
|---|---|
| Name | `trigger_daily_midnight` |
| Type | Schedule |
| Recurrence | Every 1 Day |
| At these hours | 0 (midnight) |
| At these minutes | 0 |
| Start | Today |
| Activated | Yes |

4. Click **"OK"** → **"OK"** → **"Publish all"** → **"Publish"**

> **Note:** When the trigger screen shows "This pipeline has no parameters" — this is expected and fine. The `storage_account` parameter is on each individual notebook activity, not on the pipeline itself. The trigger does not need pipeline-level parameters.

---

## 12. ADLS Lifecycle Rules + Encryption

### 12A. Create Lifecycle Rules

Lifecycle rules automatically tier or delete old data to manage storage cost.

1. Azure Portal → `stretaildatalake122` → left sidebar → **"Data management"** → **"Lifecycle management"**
2. Click **"+ Add a rule"**

**Rule 1 — Bronze archival:**
- Rule name: `archive-bronze-30d`
- Rule scope: Limit blobs using filters
- Blob type: Block blobs, Base blobs
- **Base blobs tab:**
  - Last modified > `30` days → Move to cool storage
  - Last modified > `90` days → Delete the blob
- **Filter set tab:**
  - Blob prefix: `bronze/`
- Click **"Review + add"** → **"Add"**

**Rule 2 — Silver archival:**
- Rule name: `archive-silver-60d`
- Same settings except:
  - Last modified > `60` days → Move to cool storage
  - Last modified > `180` days → Delete the blob
  - Blob prefix: `silver/`
- Click **"Review + add"** → **"Add"**

> **Why different windows?** Bronze data is raw and written once — rarely re-read after 30 days. Silver is cleaned and may be re-queried for ad-hoc analysis longer. Gold has no lifecycle rule — it is small and always queried by Synapse.

### 12B. Verify Encryption

1. In `stretaildatalake122` → left sidebar → **"Security + networking"** → **"Encryption"**
2. Verify: **Encryption type = Microsoft-managed keys** (AES-256, on by default)

3. Left sidebar → **"Settings"** → **"Configuration"**
4. Verify:
   - **Secure transfer required:** Enabled
   - **Minimum TLS version:** Version 1.2
5. If either is not set, change and **"Save"**

---

## 13. Azure Synapse Analytics

### 13A. What Synapse Does

Synapse adds a SQL interface on top of the lakehouse Gold layer. Analysts who do not know PySpark can query Gold tables with plain SQL. Power BI connects to Synapse for dashboards.

> **Important:** All Synapse queries use the **Databricks Delta outputs** (Silver and Gold Delta tables). Stream Analytics JSON output (`sales_stream_asa/`) is NOT queryable via Delta format — it is treated as raw operational logs only.

### 13B. Create Synapse Workspace

1. Azure Portal → **"+ Create a resource"** → **"Azure Synapse Analytics"** → **"Create"**
2. Fill in **Basics tab:**

| Field | Value |
|---|---|
| Subscription | Your Azure Free Trial |
| Resource group | `rg-retail-lakehouse-prod` |
| Workspace name | `synws-retail-analytics` |
| Region | Same region as everything else |
| Data Lake Storage Gen2 account | `stretaildatalake122` (select existing) |
| File system (container) | `gold` (select existing) |

3. Click **"Review + create"** → **"Create"** → **"Open Synapse Studio"**

### 13C. Verify Managed Identity Role (Check Before Adding)

When you selected `stretaildatalake122` as the linked storage during workspace creation, Azure automatically assigned Storage Blob Data Contributor to Synapse's managed identity on that storage account. Do not try to add it again — you will get "The role assignment already exists" which is expected and correct.

To verify: Azure Portal → `stretaildatalake122` → **"Access control (IAM)"** → **"Role assignments"** tab → search `synws-retail-analytics` → should show Storage Blob Data Contributor.

### 13D. Create Database and Objects

In Synapse Studio → **"Develop"** (code icon) → **"+"** → **"SQL script"**

Confirm at top: **Connect to: Built-in**, **Use database: master**

Run each block separately:

**Block 1 — Create database:**
```sql
CREATE DATABASE retail_gold
```

Switch the **"Use database"** dropdown from `master` to `retail_gold`. Then continue:

**Block 2 — Create master key** (required before any credential can be stored):
```sql
CREATE MASTER KEY ENCRYPTION BY PASSWORD = '<YOUR_SYNAPSE_MASTER_KEY_PASSWORD>';
```

**Block 3 — Create Managed Identity credential:**
```sql
CREATE DATABASE SCOPED CREDENTIAL adls_credential
WITH IDENTITY = 'Managed Identity';
```

**Block 4 — Create external data source for Gold:**
```sql
CREATE EXTERNAL DATA SOURCE gold_adls
WITH (
    LOCATION   = 'abfss://gold@stretaildatalake122.dfs.core.windows.net',
    CREDENTIAL = adls_credential
);
```

**Block 5 — Create external data source for Silver:**
```sql
-- Required because gold_adls points to /gold and cannot traverse to /silver
CREATE EXTERNAL DATA SOURCE silver_adls
WITH (
    LOCATION   = 'abfss://silver@stretaildatalake122.dfs.core.windows.net',
    CREDENTIAL = adls_credential
);
```

> **Why a separate silver_adls data source?** Each external data source is scoped to one container. A path like `gold/../silver/...` is invalid — Azure Storage does not allow container traversal. You need one data source per container.

**Block 6 — Create external file format:**
```sql
CREATE EXTERNAL FILE FORMAT delta_format
WITH (FORMAT_TYPE = DELTA);
```

**Block 7 — Create Parquet file format** (needed for CETAS — see block 12):
```sql
CREATE EXTERNAL FILE FORMAT parquet_format
WITH (FORMAT_TYPE = PARQUET);
```

**Block 8 — Create schema:**
```sql
CREATE SCHEMA gold;
```

**Block 9 — Test query on Gold data:**
```sql
SELECT *
FROM OPENROWSET(
    BULK        'sales_summary/by_product/',
    DATA_SOURCE = 'gold_adls',
    FORMAT      = 'DELTA'
) AS r
ORDER BY total_revenue DESC;
```

Expected: 5 rows — one per product with `total_orders`, `total_revenue`, `avg_order_value`, `max_order_value`, `units_sold`.

**Block 10 — Create views for clean access:**
```sql
CREATE VIEW gold.vw_sales_by_product AS
SELECT *
FROM OPENROWSET(
    BULK        'sales_summary/by_product/',
    DATA_SOURCE = 'gold_adls',
    FORMAT      = 'DELTA'
) AS r;

CREATE VIEW gold.vw_sales_by_city AS
SELECT *
FROM OPENROWSET(
    BULK        'sales_summary/by_city/',
    DATA_SOURCE = 'gold_adls',
    FORMAT      = 'DELTA'
) AS r;

CREATE VIEW gold.vw_sales_by_payment AS
SELECT *
FROM OPENROWSET(
    BULK        'sales_summary/by_payment/',
    DATA_SOURCE = 'gold_adls',
    FORMAT      = 'DELTA'
) AS r;
```

**Block 11 — Date-partitioned queries using Silver:**
```sql
-- April 2026 data only — partition pruning skips all other periods
SELECT
    product,
    city,
    COUNT(*)             AS total_orders,
    SUM(total_amount)    AS total_revenue,
    AVG(total_amount)    AS avg_order_value
FROM OPENROWSET(
    BULK        'sales_clean/',
    DATA_SOURCE = 'silver_adls',
    FORMAT      = 'DELTA'
) AS r
WHERE ingested_at >= '2026-04-01'
  AND ingested_at <  '2026-05-01'
GROUP BY product, city
ORDER BY total_revenue DESC;

-- Hourly trend
SELECT
    LEFT(CAST(ingested_at AS VARCHAR(50)), 13) AS hour_bucket,
    COUNT(*)                                   AS orders_in_hour,
    SUM(total_amount)                          AS revenue_in_hour
FROM OPENROWSET(
    BULK        'sales_clean/',
    DATA_SOURCE = 'silver_adls',
    FORMAT      = 'DELTA'
) AS r
GROUP BY LEFT(CAST(ingested_at AS VARCHAR(50)), 13)
ORDER BY hour_bucket;

-- High-value order analysis
SELECT
    city,
    product,
    COUNT(*)           AS high_value_orders,
    SUM(total_amount)  AS high_value_revenue
FROM OPENROWSET(
    BULK        'sales_clean/',
    DATA_SOURCE = 'silver_adls',
    FORMAT      = 'DELTA'
) AS r
WHERE is_high_value = 'true'
GROUP BY city, product
ORDER BY high_value_revenue DESC;
```

**Block 12 — CETAS (CREATE EXTERNAL TABLE AS SELECT):**

> **Critical limitation discovered:** `FORMAT_TYPE = DELTA` is NOT supported in CETAS for Synapse Serverless. Synapse can READ Delta but cannot WRITE Delta via CETAS. Use Parquet instead.

```sql
CREATE EXTERNAL TABLE gold.sales_apr2026_summary
WITH (
    LOCATION    = 'sales_summary/apr2026_loaded/',
    DATA_SOURCE = gold_adls,
    FILE_FORMAT = parquet_format      -- Delta WRITE not supported in CETAS; Parquet is correct
)
AS
SELECT
    product,
    city,
    COUNT(*)           AS total_orders,
    SUM(total_amount)  AS total_revenue,
    SUM(quantity)      AS units_sold,
    MIN(ingested_at)   AS first_event,
    MAX(ingested_at)   AS last_event
FROM OPENROWSET(
    BULK        'sales_clean/',
    DATA_SOURCE = 'silver_adls',
    FORMAT      = 'DELTA'
) AS r
WHERE ingested_at >= '2026-04-01'
GROUP BY product, city;

-- Verify
SELECT * FROM gold.sales_apr2026_summary ORDER BY total_revenue DESC;
```

---

## 14. Security — Managed Identity

### 14A. What Managed Identity Is

Instead of storing passwords, Azure assigns a unique Azure Active Directory identity to each service (like Synapse). Other services grant access to this identity via IAM roles — zero passwords, automatic rotation, full audit trail.

The chain for Synapse → ADLS:
```
Synapse query → uses adls_credential → which is Managed Identity
             → Azure AD resolves identity to synws-retail-analytics
             → which has Storage Blob Data Contributor on stretaildatalake122
             → access granted — no password anywhere
```

### 14B. Verify in Synapse

In Synapse Studio → run:

```sql
SELECT
    name                AS credential_name,
    credential_identity AS identity_type
FROM sys.database_scoped_credentials
WHERE name = 'adls_credential';
```

Expected output:

| credential_name | identity_type |
|---|---|
| adls_credential | Managed Identity |

### 14C. Verify in Azure Portal

1. `stretaildatalake122` → **"Access control (IAM)"** → **"Role assignments"** tab
2. Search `synws-retail-analytics` → should show: Role = Storage Blob Data Contributor

3. `synws-retail-analytics` → **"Identity"** → **"System assigned"** tab
   - Status: On
   - Object (principal) ID: a long GUID — this is Synapse's permanent AD identity

---

## 15. Final Folder Structure

```
stretaildatalake122/
│
├── bronze/
│   ├── _$azuretmpfolder$/              ← Azure internal temp (ignore)
│   ├── _checkpoints/
│   │   └── sales_stream/               ← Databricks stream progress checkpoint
│   ├── sales/
│   │   └── year=2026/
│   │       └── month=04/
│   │           ├── _delta_log/
│   │           └── part-*.snappy.parquet  ← 100 batch rows (Delta)
│   ├── sales_stream/
│   │   ├── _delta_log/
│   │   └── part-*.snappy.parquet       ← 1197 streaming rows (Delta)
│   └── sales_stream_asa/
│       └── 2026/04/04/
│           └── {HH}/                   ← ASA raw event JSON output
│
├── silver/
│   └── sales_clean/
│       ├── _delta_log/
│       ├── city=Bangalore/
│       ├── city=Chennai/
│       ├── city=Delhi/
│       ├── city=Hyderabad/
│       └── city=Mumbai/                ← 1297 cleaned rows total (Delta)
│
└── gold/
    ├── sales_summary/
    │   ├── by_product/                 ← 5 rows (Databricks Delta)
    │   ├── by_city/                    ← 5 rows (Databricks Delta)
    │   ├── by_payment/                 ← 3 rows (Databricks Delta)
    │   └── apr2026_loaded/             ← CETAS output (Parquet, from Synapse)
    └── sales_stream_asa/
        └── 2026/04/04/
            └── {HH}/                  ← ASA aggregated JSON output (tumbling window)
```

**Data format summary:**

| Path | Format | Queryable in Synapse with FORMAT = 'DELTA'? |
|---|---|---|
| `bronze/sales/` | Delta | ✅ Yes |
| `bronze/sales_stream/` | Delta | ✅ Yes |
| `bronze/sales_stream_asa/` | JSON | ❌ No — raw logs only |
| `silver/sales_clean/` | Delta | ✅ Yes |
| `gold/sales_summary/by_*/` | Delta | ✅ Yes |
| `gold/sales_summary/apr2026_loaded/` | Parquet | ✅ Yes (FORMAT = 'PARQUET') |
| `gold/sales_stream_asa/` | JSON | ❌ No — aggregated logs only |

---

## 16. Resource Summary

### All Azure Resources Created

All resources live in resource group `rg-retail-lakehouse-prod`:

| Resource | Type | Name | Key config |
|---|---|---|---|
| Storage account | ADLS Gen2 | `stretaildatalake122` | Hierarchical namespace on, LRS |
| Databricks workspace | Azure Databricks | `adb-retail-analytics` | Standard tier |
| Databricks cluster | Single Node | `Retail_Analysis_Engine` | DS3_v2, auto-terminate 30 min |
| Data Factory | ADF V2 | `adf-retail-lakehouse122` | — |
| Event Hubs namespace | Standard tier | `evhns-retail-stream` | 1 throughput unit |
| Event Hub topic | — | `retail-stream` | 2 partitions, 1-day retention |
| Stream Analytics | Cloud | `asa-retail-stream` | 1 streaming unit |
| Synapse workspace | Serverless SQL | `synws-retail-analytics` | Built-in pool, gold container linked |

### Databricks Notebooks

| Notebook | Triggered by ADF? | Purpose |
|---|---|---|
| `00_Mount_ADLS` | No | Connection test only |
| `01_Bronze_Ingestion` | ✅ Yes — ACT_Bronze_Ingestion | Generates + writes 100 batch rows to bronze |
| `02_Stream_Bronze_Ingest` | No — run manually | Reads Event Hubs, writes stream to bronze |
| `03_Silver_Transform` | ✅ Yes — ACT_Silver_Transform | Cleans + deduplicates to silver |
| `04_Gold_Aggregation` | ✅ Yes — ACT_Gold_Aggregation | Aggregates to 3 gold summary tables |

### Synapse Objects in `retail_gold`

| Object | Name | Points to |
|---|---|---|
| External data source | `gold_adls` | `abfss://gold@stretaildatalake122.dfs.core.windows.net` |
| External data source | `silver_adls` | `abfss://silver@stretaildatalake122.dfs.core.windows.net` |
| External file format | `delta_format` | FORMAT_TYPE = DELTA |
| External file format | `parquet_format` | FORMAT_TYPE = PARQUET |
| View | `gold.vw_sales_by_product` | `gold/sales_summary/by_product/` Delta |
| View | `gold.vw_sales_by_city` | `gold/sales_summary/by_city/` Delta |
| View | `gold.vw_sales_by_payment` | `gold/sales_summary/by_payment/` Delta |
| External table | `gold.sales_apr2026_summary` | `gold/sales_summary/apr2026_loaded/` Parquet |

### ADF Pipeline

| Pipeline | `PL_Retail_Lakehouse_Daily` |
|---|---|
| Activity 1 | ACT_Bronze_Ingestion → `01_Bronze_Ingestion` |
| Activity 2 | ACT_Silver_Transform → `03_Silver_Transform` (runs after 1 succeeds) |
| Activity 3 | ACT_Gold_Aggregation → `04_Gold_Aggregation` (runs after 2 succeeds) |
| Retry policy | 1 retry, 30-second interval, 12-hour timeout (all activities) |
| Trigger | `trigger_daily_midnight` — every day at 00:00 |

---

## 17. Architecture Decisions & Trade-offs

### Why Serverless SQL Pool instead of Dedicated

A Dedicated SQL Pool costs approximately $5/hour. On a $100 student credit, that is less than 20 hours of use before the account is empty. Serverless SQL Pool is pay-per-query (charged per TB scanned) — effectively free for development volumes. For production at scale, a Dedicated Pool with hash distribution on the sales fact table and date partitioning would be the correct choice.

### Why DBFS Mounts Were Not Used

Newer Databricks workspaces raise `FeatureDisabledException: DBFS mounts are not available on this workspace`. The `spark.conf.set` approach achieves the same result — registering storage credentials in the Spark session — without requiring DBFS. It is session-scoped (reset on cluster restart) so it is set at the top of every notebook.

### Why Standard Event Hubs Tier

Basic tier does not support the Kafka protocol on port 9093 — which `kafka-python` uses. Standard tier and above support Kafka. When you discover "Basic wasn't available" during creation, this is why — the portal may hide Basic when Kafka compatibility is required.

### Why Two Stream Analytics Outputs

A single ASA query with two `SELECT INTO` blocks pointing to the same output causes a compilation error. More architecturally: raw events belong in Bronze (full fidelity archive), windowed aggregations belong in Gold (business-ready summaries). Separating them enforces Medallion boundaries.

### Why CETAS Uses Parquet Not Delta

Synapse Serverless SQL Pool can READ Delta files (via `OPENROWSET` with `FORMAT = 'DELTA'`), but CETAS (CREATE EXTERNAL TABLE AS SELECT) does NOT support writing Delta format. Attempting `FILE_FORMAT = delta_format` in CETAS raises an error. The workaround is Parquet for CETAS output — it is still efficiently queryable and integrates cleanly with Synapse.

### Components Not Implemented (Student Credit Constraints)

| Component | Why skipped |
|---|---|
| Self-hosted Integration Runtime | Requires a separate VM — significant cost |
| Private Link | Requires Virtual Network setup — additional networking cost |
| CI/CD with Azure DevOps | Out of scope for this implementation phase |
| IoT Hub | Marked as "concept" in the case study; Event Hubs covers the use case |
| Auto-scaling job clusters | Requires higher-tier Databricks plan |

---

*End of from-scratch implementation guide.*

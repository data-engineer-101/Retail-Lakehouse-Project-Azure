# Retail Lakehouse & Real-Time Analytics Platform on Azure
## Implementation Documentation

**Prepared for:** Course Instructor  
**Project Type:** Azure Data Engineering — End-to-End Lakehouse  
**Environment:** Azure Student Account ($100 credit)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Core Azure Infrastructure](#2-core-azure-infrastructure)
3. [Storage Layer — ADLS Gen2](#3-storage-layer--adls-gen2)
4. [Processing Layer — Azure Databricks (Lakehouse)](#4-processing-layer--azure-databricks)
5. [Integration Layer — Azure Data Factory](#5-integration-layer--azure-data-factory)
6. [Streaming Stack — Event Hubs + Stream Analytics](#6-streaming-stack)
7. [Analytics Layer — Azure Synapse Analytics](#7-analytics-layer--azure-synapse-analytics)
8. [Security & Governance](#8-security--governance)
9. [Architecture Decisions](#9-architecture-decisions)
10. [Resource Summary](#10-resource-summary)

---

## 1. Project Overview

### Problem Statement

A global retail chain operating both physical stores and an e-commerce platform faces four core data challenges: disconnected systems (POS, website, warehouse, IoT sensors) that cannot share data; delayed reporting relying on daily batch jobs with no real-time visibility; poor inventory management causing stock-outs; and no unified customer data for personalisation.

### Solution

A modern cloud data platform built on Azure implementing the **Medallion Lakehouse Architecture** — a three-layer data design (Bronze → Silver → Gold) that centralises all retail data, supports both batch and real-time analytics, enables advanced reporting, and enforces security and cost governance.

### Technology Stack

| Layer | Service | Purpose |
|---|---|---|
| Storage | Azure Data Lake Storage Gen2 | Persistent lakehouse storage |
| Processing | Azure Databricks | Batch data transformation |
| Integration | Azure Data Factory | Pipeline orchestration |
| Streaming Ingest | Azure Event Hubs | Real-time event ingestion |
| Stream Processing | Azure Stream Analytics | Windowed real-time aggregation |
| Analytics | Azure Synapse Analytics | SQL querying over Gold layer |

### Architecture Overview

> 📷 **[Image: End-to-end architecture diagram — Batch Layer + Streaming Layer + Consumption Layer]**

**Batch flow:**
POS / E-commerce / ERP → ADF Pipelines → ADLS Bronze → Databricks Silver → Databricks Gold → Synapse SQL Pool → Power BI

**Streaming flow:**
POS Events → Event Hubs → Stream Analytics (Tumbling Window) → ADLS Bronze → Synapse

---

## 2. Core Azure Infrastructure

### Subscription

| Field | Value |
|---|---|
| Type | Azure Free Trial (Student) |
| Budget | $100 credit |
| Purpose | Billing container for all project resources |

### Resource Group

| Field | Value |
|---|---|
| Name | `rg-retail-lakehouse-prod` |
| Purpose | Logical folder grouping all project Azure resources |
| Benefit | Single-click cleanup — delete resource group to remove everything |

**Why a resource group?** Azure resources don't exist in isolation — they need a management container. The resource group `rg-retail-lakehouse-prod` acts as a project folder so all services (storage, Databricks, ADF, Synapse, Event Hubs) are managed, monitored, and billed together.

---

## 3. Storage Layer — ADLS Gen2

### Storage Account

| Field | Value |
|---|---|
| Resource name | `stretaildatalake122` |
| Type | Azure Data Lake Storage Gen2 |
| Hierarchical namespace | Enabled (required for ADLS Gen2 folder semantics) |
| Replication | Locally Redundant Storage (LRS) |
| Access tier | Hot (default — changed by lifecycle rules for old data) |

**Why ADLS Gen2?** Unlike regular Azure Blob Storage, ADLS Gen2 supports hierarchical namespaces (true folder structure, not simulated), which enables efficient partition-aware queries. Databricks and Synapse both treat ADLS Gen2 paths as first-class citizens with built-in optimisation.

> 📷 **[Image: Azure Portal — stretaildatalake122 overview page]**

---

### Container Structure

Three containers were created implementing the Medallion Architecture:

| Container | Purpose | Data Quality |
|---|---|---|
| `bronze` | Raw data exactly as received — no changes | Unvalidated, may have duplicates |
| `silver` | Cleaned, deduplicated, type-corrected data | Trusted, validated |
| `gold` | Pre-aggregated business summaries | Business-ready, optimised for queries |

**Why three layers?** Each layer serves a different consumer. Data engineers work in bronze, analysts trust silver, and business users and dashboards consume gold. Separating them means a bug in a transformation never corrupts the raw source data.

> 📷 **[Image: Storage Browser showing bronze, silver, gold containers]**

---

### Folder Hierarchy

```
stretaildatalake122/
├── bronze/
│   ├── sales/
│   │   └── year=2026/
│   │       └── month=04/          ← Batch ingested Delta files
│   ├── sales_stream/              ← Databricks stream output (Delta)
│   └── sales_stream_asa/
│       └── 2026/04/04/HH/         ← Stream Analytics output (JSON)
│
├── silver/
│   └── sales_clean/
│       ├── city=Bangalore/        ← Partitioned by city
│       ├── city=Delhi/
│       ├── city=Mumbai/
│       ├── city=Chennai/
│       └── city=Hyderabad/
│
└── gold/
    └── sales_summary/
        ├── by_product/            ← 5 rows, one per product
        ├── by_city/               ← 5 rows, one per city
        ├── by_payment/            ← 3 rows, one per payment method
        └── apr2026_loaded/        ← CETAS materialised table
```

**Why `year=YYYY/month=MM` naming?** This is Hive-style partitioning — Databricks and Synapse automatically recognise this pattern. When querying `WHERE month = '04'`, the engine skips all other month folders without reading them, dramatically improving query speed on large datasets.

**Why partition Silver by city?** City is a common filter in retail analytics (regional sales reports, city-level inventory). Partitioning by city means a query for Bangalore data reads only the `city=Bangalore/` folder — not all 5 city folders.

> 📷 **[Image: Storage Browser — bronze/sales/year=2026/month=04/ showing Delta Parquet files and _delta_log/]**

> 📷 **[Image: Storage Browser — silver/sales_clean/ showing city=* partition folders]**

---

### Delta Format

All Databricks-written data uses Delta Lake format. Delta stores data as Parquet files (compressed, columnar — fast for analytics) plus a `_delta_log/` transaction log folder. This provides ACID transactions, schema enforcement, time travel (query data as of any previous point in time), and automatic file compaction.

---

### Lifecycle Rules

Two automated rules manage storage cost:

| Rule Name | Container | Action 1 | Action 2 |
|---|---|---|---|
| `archive-bronze-30d` | bronze | Move to Cool tier after 30 days | Delete after 90 days |
| `archive-silver-60d` | silver | Move to Cool tier after 60 days | Delete after 180 days |

**Why Cool tier?** Azure storage has three tiers — Hot (fast, expensive), Cool (slower, ~50% cheaper), and Archive (cheapest, hours to retrieve). Raw Bronze data is written once and rarely re-read after 30 days — moving it to Cool saves cost without impacting active workloads.

> 📷 **[Image: Lifecycle management rules list showing both rules]**

---

### Encryption

| Setting | Value |
|---|---|
| Encryption at rest | Microsoft-managed keys, AES-256 |
| Encryption in transit | HTTPS enforced (Secure Transfer Required: Enabled) |
| Minimum TLS version | 1.2 |

All data written to ADLS is encrypted at rest by default using AES-256. Secure transfer ensures no unencrypted HTTP connections are accepted. These settings are verified in the Encryption and Configuration blades of the storage account.

> 📷 **[Image: Storage account Encryption blade showing Microsoft-managed keys]**

> 📷 **[Image: Storage account Configuration blade showing Secure Transfer = Enabled, TLS 1.2]**

---

## 4. Processing Layer — Azure Databricks

### Workspace

| Field | Value |
|---|---|
| Resource name | `adb-retail-analytics` |
| Purpose | Managed Spark environment for data transformation |

**Why Databricks?** Apache Spark (the engine inside Databricks) is purpose-built for processing large datasets in parallel across a cluster. It natively reads and writes Delta format, handles both batch and streaming workloads, and integrates directly with ADLS Gen2 via the `wasbs://` protocol.

> 📷 **[Image: Databricks workspace home page]**

---

### Cluster

| Field | Value |
|---|---|
| Name | `Retail_Analysis_Engine` |
| Type | Single Node |
| VM size | Standard_DS3_v2 (4 vCPUs, 14 GB RAM) |
| Auto-terminate | After 30 minutes of inactivity |
| Runtime | Databricks Runtime (latest LTS) |

**Why Single Node for this project?** Single Node is sufficient for development and learning — it eliminates the need to manage worker nodes and reduces cost. Production deployments would use auto-scaling multi-node clusters (job clusters spun up per pipeline run, then terminated).

**Why auto-terminate at 30 minutes?** Databricks clusters cost money while running even with no active work. Auto-termination ensures the cluster shuts down after idle time — critical for managing student credit budget.

> 📷 **[Image: Databricks cluster configuration page showing Retail_Analysis_Engine]**

---

### ADLS Integration

Databricks connects to ADLS using `spark.conf.set` to register the storage account key in the active Spark session. This is set at the top of every notebook. The full ADLS path format used throughout is:

```
wasbs://{container}@stretaildatalake122.blob.core.windows.net/{path}
```

A helper function `adls_path(container, subfolder)` is defined in every notebook config cell for clean path construction.

---

### Notebooks Created

| Notebook | Purpose |
|---|---|
| `00_Mount_ADLS` | Initial connection test — verifies ADLS accessibility |
| `01_Bronze_Ingestion` | Generates 100 simulated retail orders, writes to bronze as Delta |
| `02_Stream_Bronze_Ingest` | Reads live events from Event Hubs, writes stream to bronze |
| `03_Silver_Transform` | Reads both bronze sources, cleans and deduplicates, writes to silver |
| `04_Gold_Aggregation` | Reads silver, produces 3 aggregated Gold tables |

> 📷 **[Image: Databricks workspace showing all 4 notebooks in file tree]**

---

### Bronze → Silver → Gold Transformation Logic

**Bronze (raw):** 100 batch orders + 1197 stream events land exactly as generated. No validation, no cleaning. Schema: `order_id, product, price, quantity, total_amount, city, payment_method, event_time`.

**Silver (clean):** The `03_Silver_Transform` notebook applies these rules:
- Removes duplicate `order_id` values (network retries can send the same event twice)
- Drops rows where critical fields (`order_id`, `product`, `price`, `total_amount`) are null
- Converts `event_time` from string to proper timestamp type
- Trims whitespace from all text columns
- Adds `is_high_value` boolean flag where `total_amount > 40000`
- Adds `source` column marking each row as either `batch` or `stream`

Result: 1297 clean rows, partitioned by city.

**Gold (aggregated):** Three summary tables written by `04_Gold_Aggregation`:
- `by_product`: 5 rows — total orders, revenue, avg value, max value, units sold per product
- `by_city`: 5 rows — total orders, revenue, avg order value per city
- `by_payment`: 3 rows — total orders, revenue, percentage of orders per payment method

> 📷 **[Image: Databricks notebook showing Silver transform output — display(df_silver.limit(10))]**

> 📷 **[Image: Databricks notebook showing Gold by_product table output]**

---

## 5. Integration Layer — Azure Data Factory

### Workspace

| Field | Value |
|---|---|
| Resource name | `adf-retail-lakehouse122` |
| Purpose | Orchestration — schedules and monitors the Bronze → Silver → Gold pipeline |
| Version | V2 |

**Why ADF?** Without ADF, a data engineer must manually run 3 notebooks every day. ADF automates this with a scheduled pipeline, handles dependencies (Silver only runs after Bronze succeeds), retries on failure, and provides a monitoring dashboard showing every run's history.

> 📷 **[Image: ADF Studio home page]**

---

### Linked Services

Two connections were configured — these are saved, reusable credentials:

| Name | Connects to | Auth method |
|---|---|---|
| `ls_databricks_retail` | `adb-retail-analytics` Databricks workspace | Personal Access Token |
| `ls_adls_retail` | `stretaildatalake122` storage account | Account Key |

---

### Pipeline

| Field | Value |
|---|---|
| Pipeline name | `PL_Retail_Lakehouse_Daily` |
| Type | Sequential notebook execution |
| Activities | 3 Databricks Notebook activities connected in series |

> 📷 **[Image: ADF pipeline canvas showing 3 connected activity boxes]**

---

### Activities and Retry Policy

Each activity runs one Databricks notebook and passes the `storage_account` parameter:

| Activity name | Notebook | Retry | Retry interval | Timeout |
|---|---|---|---|---|
| `ACT_Bronze_Ingestion` | `01_Bronze_Ingestion` | 1 | 30 seconds | 12 hours |
| `ACT_Silver_Transform` | `03_Silver_Transform` | 1 | 30 seconds | 12 hours |
| `ACT_Gold_Aggregation` | `04_Gold_Aggregation` | 1 | 30 seconds | 12 hours |

**Why retry = 1, interval = 30 seconds?** Databricks cluster startup, network blips, and API throttling are common transient failures. One retry with a 30-second wait covers the vast majority of these without alerting. Two retries would delay failure detection unnecessarily.

**Why sequential (not parallel)?** Silver depends on Bronze being complete. Gold depends on Silver. Running them in parallel would cause Silver to read an incomplete Bronze table. The green arrow connectors enforce this dependency.

---

### Trigger

| Field | Value |
|---|---|
| Trigger name | `trigger_daily_midnight` |
| Type | Schedule |
| Recurrence | Every 1 day |
| Time | 00:00 (midnight) |
| Status | Started (active) |

**Why midnight?** Retail data from the previous day is fully available by midnight — sales close, POS systems flush their queues, and the pipeline runs on a complete dataset. Morning reports are ready before store managers arrive.

---

### Monitoring Dashboard

The ADF Monitor section provides:
- **Pipeline runs:** full history of every execution with duration and status
- **Activity runs:** per-activity drill-down showing which notebook took how long
- **Trigger runs:** confirmation the daily schedule is active and tracking next run time
- **Gantt view:** sequential timeline showing Bronze → Silver → Gold execution order

> 📷 **[Image: ADF Monitor — Pipeline runs list showing Succeeded status]**

> 📷 **[Image: ADF Monitor — Activity runs drill-down showing 3 activities]**

---

## 6. Streaming Stack

### Event Hubs

| Field | Value |
|---|---|
| Namespace name | `evhns-retail-stream` |
| Pricing tier | Standard (required for Kafka protocol support) |
| Throughput units | 1 |
| Topic name | `retail-stream` |
| Partition count | 2 |
| Message retention | 1 day |

**Why Event Hubs?** Event Hubs is a fully managed, high-throughput message broker — Azure's equivalent of Apache Kafka. It decouples the data producer (your generator script) from consumers (Databricks, Stream Analytics) so either side can go down independently without data loss.

**Why Standard tier and not Basic?** The Kafka protocol (port 9093) that the stream generator uses is only available on Standard tier and above. Basic tier supports only the AMQP protocol.

> 📷 **[Image: Event Hubs namespace overview showing retail-stream topic]**

> 📷 **[Image: Event Hub metrics — Incoming Messages graph ticking up during generator run]**

---

### Stream Generator

The file `retail_stream_generator.py` runs locally and simulates a live retail POS system. It sends one order event per second to the `retail-stream` Event Hub topic using the Kafka protocol. Each event contains: `order_id, product, price, quantity, total_amount, city, payment_method, event_time`.

Configuration values used:
- `BOOTSTRAP_SERVERS`: `evhns-retail-stream.servicebus.windows.net:9093`
- `TOPIC_NAME`: `retail-stream`
- `CONNECTION_STRING`: Event Hub namespace primary connection string with `EntityPath=retail-stream` appended

---

### Databricks Streaming (02_Stream_Bronze_Ingest)

The notebook `02_Stream_Bronze_Ingest` uses Spark Structured Streaming to read from Event Hubs via the Kafka protocol, parse the JSON events, and write continuously to `bronze/sales_stream/` as Delta. Key configuration: `kafkashaded.org.apache.kafka` prefix (Databricks-specific), `startingOffsets: earliest`, trigger every 10 seconds.

Result: 1197 stream events landed in bronze during testing.

> 📷 **[Image: Databricks streaming notebook cell showing stream running with micro-batch output]**

---

### Azure Stream Analytics Job

| Field | Value |
|---|---|
| Resource name | `asa-retail-stream` |
| Streaming units | 1 |
| Input alias | `retail-eh-input` |
| Input source | `evhns-retail-stream` → `retail-stream` topic |
| Output alias | `retail-adls-output` |
| Output destination | `bronze/sales_stream_asa/{date}/{time}/` |
| Output format | JSON, line separated |

**Why Stream Analytics as a separate service?** Stream Analytics is a fully managed, always-on stream processing service that runs independently of Databricks. It applies SQL-based windowing queries directly on the incoming stream without needing a cluster. This is the architecturally clean solution — Databricks handles batch, Stream Analytics handles real-time.

---

### Tumbling Window Query

The Stream Analytics job applies a 1-minute tumbling window aggregation — grouping all events that arrive within each 60-second window by product, city, and payment method, then writing one summary row per group. This matches the exact query pattern specified in the case study.

Every 60 seconds, regardless of event volume, Stream Analytics outputs a clean summary to ADLS. The output path pattern `{date}/{time}` automatically creates partitioned folders like `2026/04/04/14/` for each hour.

> 📷 **[Image: Stream Analytics job overview showing Running status]**

> 📷 **[Image: Stream Analytics metrics — Input Events and Output Events graphs]**

> 📷 **[Image: Storage Browser — bronze/sales_stream_asa/ showing date-partitioned JSON output files]**

---

## 7. Analytics Layer — Azure Synapse Analytics

### Workspace

| Field | Value |
|---|---|
| Resource name | `synws-retail-analytics` |
| Pool type | Serverless SQL Pool (Built-in) |
| Linked storage | `stretaildatalake122` / `gold` container |

**Why Synapse?** Synapse adds a SQL layer on top of the lakehouse — business analysts who don't know PySpark can query Gold tables with plain SQL, and Power BI connects directly to Synapse for live dashboards. It democratises data access beyond the data engineering team.

**Why Serverless (not Dedicated)?** A Dedicated SQL Pool costs approximately $5/hour and would exhaust the student credit budget in under 20 hours. Serverless SQL Pool is pay-per-query (charged per TB scanned) — ideal for development and intermittent querying. See Architecture Decisions section.

> 📷 **[Image: Synapse Studio home page]**

---

### Database Objects Created

All objects live in the `retail_gold` database on the Built-in serverless pool:

| Object type | Name | Purpose |
|---|---|---|
| Database | `retail_gold` | Dedicated namespace for all retail analytics objects |
| Master key | (system) | Required by Synapse before any credential can be stored |
| Scoped credential | `adls_credential` | Managed Identity token for ADLS access (no password) |
| External data source | `gold_adls` | Points to `abfss://gold@stretaildatalake122.dfs.core.windows.net` |
| External file format | `delta_format` | Registers Delta as a known file format |
| Schema | `gold` | Organises views and external tables |
| View | `gold.vw_sales_by_product` | Live view over Gold by_product/ Delta files |
| View | `gold.vw_sales_by_city` | Live view over Gold by_city/ Delta files |
| View | `gold.vw_sales_by_payment` | Live view over Gold by_payment/ Delta files |
| External table | `gold.sales_apr2026_summary` | CETAS — materialised April 2026 summary |

---

### COPY INTO / CETAS Pattern

The case study specifies COPY INTO for bulk data loading. Since Serverless SQL Pool does not support COPY INTO (that command targets Dedicated SQL Pool), the equivalent pattern is CETAS — CREATE EXTERNAL TABLE AS SELECT. CETAS reads from Silver/Gold Delta files, applies transformations, and writes a new materialised external table to ADLS in one command — achieving identical results without a dedicated cluster.

> 📷 **[Image: Synapse Studio SQL script showing query results from gold.vw_sales_by_product]**

> 📷 **[Image: Synapse Studio showing all views under retail_gold > gold schema]**

---

### Date-Partitioned Queries

Synapse queries against Delta files support partition pruning via WHERE clauses on the `ingested_at` column. A query filtered to April 2026 scans only the relevant data slice — on a dataset with years of history this provides orders-of-magnitude query performance improvement.

Hourly trend queries aggregate orders and revenue by hour bucket — enabling store managers to see real-time sales momentum throughout the day.

---

## 8. Security & Governance

### Managed Identity

**What it is:** Instead of storing passwords or connection strings, Azure assigns a unique identity (backed by Azure Active Directory) to each service. Other services grant access to this identity through IAM roles — no passwords involved anywhere in the chain.

| Field | Value |
|---|---|
| Identity type | System-assigned Managed Identity |
| Principal name | `synws-retail-analytics` |
| Assigned role | Storage Blob Data Contributor |
| Role assigned on | `stretaildatalake122` (ADLS) |
| Credential name in Synapse | `adls_credential` (identity = Managed Identity) |

**Verification:** The `sys.database_scoped_credentials` system view in Synapse confirms the credential uses Managed Identity, not a password. The ADLS IAM → Role assignments blade confirms the assignment exists.

> 📷 **[Image: Synapse Identity blade showing System assigned = On with Object ID]**

> 📷 **[Image: ADLS Access Control (IAM) — Role assignments showing synws-retail-analytics as Storage Blob Data Contributor]**

---

### Encryption Summary

| Layer | Mechanism | Status |
|---|---|---|
| Data at rest (ADLS) | AES-256, Microsoft-managed keys | ✅ Enabled by default |
| Data in transit | HTTPS / TLS 1.2 | ✅ Enforced via Secure Transfer |
| Data in Databricks | Encrypted cluster storage | ✅ Managed by Azure |
| Data in Synapse | Serverless queries use ADLS encryption | ✅ Inherited |

---

### Lifecycle Policy Summary

| Rule | Scope | Tier change | Deletion |
|---|---|---|---|
| `archive-bronze-30d` | `bronze/` | Cool after 30 days | Delete after 90 days |
| `archive-silver-60d` | `silver/` | Cool after 60 days | Delete after 180 days |
| Gold layer | No rule | Always Hot | No automatic deletion |

Gold data is kept hot permanently — it is small (only aggregated summaries) and actively queried by Synapse and Power BI, so there is no cost benefit to archiving it.

---

## 9. Architecture Decisions

The following components from the case study were not implemented, with justification:

| Component | Reason not implemented | Impact |
|---|---|---|
| Dedicated SQL Pool | ~$5/hour cost — would exhaust $100 student credit in under 20 hours of use | Serverless pool provides equivalent functionality for development |
| Self-hosted Integration Runtime | Requires provisioning a separate VM in the student subscription — adds significant cost and complexity | Azure IR used instead; self-hosted IR needed only for on-premises data sources |
| Private Link | Requires Virtual Network configuration and additional cost | Not feasible on student credit; Managed Identity provides authentication security |
| CI/CD with Azure DevOps | Requires Azure DevOps organisation setup, out of scope for this implementation | Notebooks published manually; production deployments would add this |
| IoT Hub | The case study marks IoT Hub as a conceptual component ("smart shelves concept") | No physical IoT devices available; Event Hubs covers the streaming ingestion use case |
| Auto-scaling job clusters | Requires paid plan above Basic tier | Single Node cluster with auto-terminate used; cost-equivalent for development scale |

All decisions prioritise functional completeness within the student credit constraint while demonstrating the correct architectural pattern for each component.

---

## 10. Resource Summary

All resources created in `rg-retail-lakehouse-prod`:

| Resource | Type | Name | Region |
|---|---|---|---|
| Storage account | ADLS Gen2 | `stretaildatalake122` | [your region] |
| Databricks workspace | Azure Databricks | `adb-retail-analytics` | [your region] |
| Data Factory | ADF V2 | `adf-retail-lakehouse122` | [your region] |
| Event Hubs namespace | Standard tier | `evhns-retail-stream` | [your region] |
| Event Hub topic | — | `retail-stream` | — |
| Stream Analytics | 1 SU | `asa-retail-stream` | [your region] |
| Synapse workspace | Serverless | `synws-retail-analytics` | [your region] |

### Key Paths Reference

| Path | Contents |
|---|---|
| `bronze/sales/year=2026/month=04/` | 100 batch Delta records |
| `bronze/sales_stream/` | 1197+ streaming Delta records |
| `bronze/sales_stream_asa/{date}/{time}/` | Stream Analytics JSON output |
| `silver/sales_clean/city=*/` | 1297 cleaned, deduplicated rows |
| `gold/sales_summary/by_product/` | 5-row product summary |
| `gold/sales_summary/by_city/` | 5-row city summary |
| `gold/sales_summary/by_payment/` | 3-row payment method summary |
| `gold/sales_summary/apr2026_loaded/` | CETAS materialised table |

### Evaluation Rubric Mapping

| Criteria | Weight | Implementation |
|---|---|---|
| Architecture Design | 20% | Medallion lakehouse, end-to-end flow, all layers implemented |
| ADF Pipelines | 15% | PL_Retail_Lakehouse_Daily, linked services, triggers, retry policy |
| Lakehouse Implementation | 20% | Bronze→Silver→Gold with Delta, partitioning, cleaning logic |
| Streaming Implementation | 15% | Event Hubs + Stream Analytics tumbling window + Databricks stream |
| Synapse Optimization | 15% | Serverless pool, views, CETAS, date-partitioned queries |
| Security & Governance | 10% | Managed Identity, AES-256, TLS 1.2, lifecycle rules |
| Documentation | 5% | This document |

---

*End of Implementation Documentation*

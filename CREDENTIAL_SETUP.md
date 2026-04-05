# Credential Setup Guide — Retail Lakehouse Project

This guide explains how to set up the **Databricks Secret Scope** that all
notebooks now use instead of hardcoded credentials.
Run these steps **once** before running any notebook.

---

## All Credentials Reference

| What | Value |
|---|---|
| ADLS storage account | `stretaildatalake122` |
| ADLS key (adls-key) | `<YOUR_ADLS_STORAGE_KEY>` |
| Event Hub namespace | `evhns-retail-stream` |
| Event Hub topic | `retail-stream` |
| EH connection string (eh-connection-string) | `Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<YOUR_EH_SHARED_ACCESS_KEY>` |
| Databricks PAT (databricks-pat) | Full token from Databricks → Settings → Developer → Access Tokens |
| Synapse master key password | `<YOUR_SYNAPSE_MASTER_KEY_PASSWORD>` |
| Secret Scope name | `retail-secrets` |

---

## Step 1 — Create a Databricks-backed Secret Scope (no Azure Key Vault needed)

1. In your Databricks workspace, go to:  
   `https://<your-databricks-url>#secrets/createScope`  
   (e.g. `https://<YOUR_DATABRICKS_WORKSPACE_URL>#secrets/createScope`)

2. Fill in:
   - **Scope Name:** `retail-secrets`
   - **Manage Principal:** All Users
   - **Backend Type:** Databricks  
     *(Choose this for Student account — Azure Key Vault requires a Premium Databricks tier)*

3. Click **Create**.

---

## Step 2 — Add Secrets (via Databricks CLI)

Install the CLI if not already installed:
```bash
pip install databricks-cli
databricks configure --token
# Paste: Host = https://<YOUR_DATABRICKS_WORKSPACE_URL>
#        Token = <your Databricks PAT>
```

Then add the two required secrets:
```bash
# ADLS storage key
databricks secrets put --scope retail-secrets --key adls-key
# When prompted, paste:
# <YOUR_ADLS_STORAGE_KEY>

# Event Hub connection string (WITHOUT EntityPath — notebooks append it dynamically)
databricks secrets put --scope retail-secrets --key eh-connection-string
# When prompted, paste:
# Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<YOUR_EH_SHARED_ACCESS_KEY>
```

---

## Step 3 — Verify in a Databricks Notebook

Run this in any notebook cell to confirm:
```python
# Should print the key without errors (value is redacted in output)
key = dbutils.secrets.get(scope="retail-secrets", key="adls-key")
print(f"Key loaded — length: {len(key)} chars")  # Expected: 88
```

---

## Step 4 — Local Stream Generator (.env file)

Create a `.env` file next to `retail_stream_generator.py` with:
```
EH_CONNECTION_STRING=Endpoint=sb://evhns-retail-stream.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<YOUR_EH_SHARED_ACCESS_KEY>
```

Install dependencies and run:
```bash
pip install kafka-python python-dotenv
python retail_stream_generator.py
```

---

## Security Notes

- The `.env` file and this guide are **personal references only** — do not share or commit to Git.
- The `dbutils.secrets.get()` calls in notebooks print `[REDACTED]` — credentials are never shown in cell output.
- If keys are rotated in Azure Portal, update the Databricks secret scope and `.env` file.

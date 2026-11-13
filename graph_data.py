"""Reads the SENTINEL kit tables and turns them into plain rows for Neo4j.
No database code in here, so it can be tested on its own (see 02_load_graph.py --dry-run)."""
import glob
import json
import math
import os
import sys

import pandas as pd


def read_table(data_dir: str, name: str) -> pd.DataFrame:
    """Read every csv.gz shard of one table (all splits)."""
    files = sorted(glob.glob(os.path.join(data_dir, name, "*", "*.csv.gz")))
    if not files:
        sys.exit(f"No files found for table '{name}' under DATA_DIR={data_dir!r}.\n"
                 "Unzip supabase_db_kit into this folder and point DATA_DIR at its data/tables folder.")
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def clean(v):
    """numpy / NaN -> plain Python values the Neo4j driver accepts."""
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def city_of(value):
    """merchant_location is a JSON string like {"city":"Jaipur","lat":26.9,"lon":75.8}."""
    try:
        return json.loads(value).get("city") if isinstance(value, str) else None
    except ValueError:
        return None


def load_transactions(data_dir: str) -> pd.DataFrame:
    tx = read_table(data_dir, "transactions")
    labels = read_table(data_dir, "labels")[["transaction_id", "fraud_label"]]
    df = tx.merge(labels, on="transaction_id", how="left", validate="one_to_one")
    if df["fraud_label"].isna().any():
        sys.exit("Some transactions have no label - check the labels table.")
    df["transaction_time"] = pd.to_datetime(df["transaction_time"], utc=True)
    return df


def sample_keep_clusters(df: pd.DataFrame, target: int) -> pd.DataFrame:
    """Pick whole customers until we have at least `target` transactions.

    Customers who share a device with another customer are taken FIRST. A plain random
    sample would cut most shared-device clusters apart and the graph would show nothing.
    """
    if target <= 0:
        return df
    per_device = df.dropna(subset=["device_id"]).groupby("device_id")["customer_id"].nunique()
    shared_devices = per_device[per_device >= 2].index
    first = df[df["device_id"].isin(shared_devices)]["customer_id"].unique().tolist()
    chosen = list(first)
    counts = df.groupby("customer_id").size()
    total = counts.loc[chosen].sum() if chosen else 0
    rest = counts.drop(index=chosen).sample(frac=1.0, random_state=42)
    for cid, n in rest.items():
        if total >= target:
            break
        chosen.append(cid)
        total += n
    return df[df["customer_id"].isin(set(chosen))]


def build_rows(df, customers, devices, merchants):
    """Returns five lists of dicts: customers, devices, merchants, used_device, paid."""
    kind = dict(zip(devices["device_id"], devices["device_kind"]))
    cust = customers.set_index("customer_id")
    merch = merchants.set_index("merchant_id")

    customer_rows = [{
        "customer_id": cid,
        "age": clean(cust.at[cid, "customer_age"]),
        "home_city": clean(cust.at[cid, "home_city"]),
        "region": clean(cust.at[cid, "region"]),
    } for cid in df["customer_id"].unique()]

    device_rows = [{"device_id": did, "kind": kind.get(did)}
                   for did in df["device_id"].dropna().unique()]

    merchant_rows = [{
        "merchant_id": mid,
        "category": clean(merch.at[mid, "merchant_category"]),
        "city": city_of(merch.at[mid, "merchant_location"]),
    } for mid in df["merchant_id"].unique()]

    with_dev = df.dropna(subset=["device_id"])
    g = with_dev.groupby(["customer_id", "device_id"])["transaction_time"].agg(["min", "max", "size"])
    used_rows = [{
        "customer_id": c, "device_id": d,
        "first_seen": r["min"].isoformat(), "last_seen": r["max"].isoformat(),
        "txn_count": int(r["size"]),
    } for (c, d), r in g.iterrows()]

    paid_rows = [{
        "transaction_id": r["transaction_id"],
        "customer_id": r["customer_id"],
        "merchant_id": r["merchant_id"],
        "device_id": clean(r["device_id"]),
        "amount": r["amount_paise"] / 100,
        "time": r["transaction_time"].isoformat(),     # converted with datetime() inside Cypher
        "fraud_label": int(r["fraud_label"]),
    } for r in df.to_dict("records")]
    return customer_rows, device_rows, merchant_rows, used_rows, paid_rows

"""Step 2: load SENTINEL into Neo4j as a graph.

Nodes:         (:Customer) (:Device) (:Merchant)
Relationships: (:Customer)-[:USED_DEVICE]->(:Device)
               (:Customer)-[:PAID {transaction_id, amount, time, fraud_label, device_id}]->(:Merchant)

Everything uses MERGE, so you can run this script twice: the second run creates 0 new nodes
and 0 new relationships. Uniqueness constraints are created first.
Use  --dry-run  to see what would be loaded without connecting to Neo4j.
"""
import sys

from config import DATA_DIR, NEO4J_DATABASE, TARGET_TXNS, get_driver
from graph_data import build_rows, load_transactions, read_table, sample_keep_clusters

BATCH = 2000

CONSTRAINTS = [
    "CREATE CONSTRAINT customer_id_unique IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
    "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
    "CREATE CONSTRAINT merchant_id_unique IF NOT EXISTS FOR (m:Merchant) REQUIRE m.merchant_id IS UNIQUE",
]
# Optional (Neo4j 5.7+): also makes each PAID edge unique by transaction_id and speeds up MERGE
PAID_CONSTRAINT = ("CREATE CONSTRAINT paid_txn_unique IF NOT EXISTS "
                   "FOR ()-[p:PAID]-() REQUIRE p.transaction_id IS UNIQUE")

LOAD_CUSTOMERS = """
UNWIND $rows AS row
MERGE (c:Customer {customer_id: row.customer_id})
SET c.age = row.age, c.home_city = row.home_city, c.region = row.region"""

LOAD_DEVICES = """
UNWIND $rows AS row
MERGE (d:Device {device_id: row.device_id})
SET d.kind = row.kind"""

LOAD_MERCHANTS = """
UNWIND $rows AS row
MERGE (m:Merchant {merchant_id: row.merchant_id})
SET m.category = row.category, m.city = row.city"""

LOAD_USED_DEVICE = """
UNWIND $rows AS row
MATCH (c:Customer {customer_id: row.customer_id})
MATCH (d:Device {device_id: row.device_id})
MERGE (c)-[u:USED_DEVICE]->(d)
SET u.first_seen = datetime(row.first_seen), u.last_seen = datetime(row.last_seen),
    u.txn_count = row.txn_count"""

LOAD_PAID = """
UNWIND $rows AS row
MATCH (c:Customer {customer_id: row.customer_id})
MATCH (m:Merchant {merchant_id: row.merchant_id})
MERGE (c)-[p:PAID {transaction_id: row.transaction_id}]->(m)
SET p.amount = row.amount, p.time = datetime(row.time),
    p.fraud_label = row.fraud_label, p.device_id = row.device_id"""


def counts(session):
    nodes = {r["label"]: r["n"] for r in session.run(
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n")}
    rels = {r["type"]: r["n"] for r in session.run(
        "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n")}
    return nodes, rels


def load(session, query, rows, label):
    created_nodes = created_rels = 0
    for i in range(0, len(rows), BATCH):
        summary = session.execute_write(
            lambda tx, chunk=rows[i:i + BATCH]: tx.run(query, rows=chunk).consume())
        created_nodes += summary.counters.nodes_created
        created_rels += summary.counters.relationships_created
    print(f"  {label:<12} {len(rows):>7} rows   new nodes: {created_nodes:>5}   new relationships: {created_rels:>6}")


def main():
    dry = "--dry-run" in sys.argv
    df = sample_keep_clusters(load_transactions(DATA_DIR), TARGET_TXNS)
    cust, dev, mer, used, paid = build_rows(
        df, read_table(DATA_DIR, "customers"), read_table(DATA_DIR, "devices"),
        read_table(DATA_DIR, "merchants"))
    print(f"Prepared: {len(cust)} customers, {len(dev)} devices, {len(mer)} merchants, "
          f"{len(used)} USED_DEVICE, {len(paid)} PAID (transactions), "
          f"{sum(r['fraud_label'] for r in paid)} fraud-labelled")
    if dry:
        return

    driver = get_driver()
    driver.verify_connectivity()
    with driver.session(database=NEO4J_DATABASE) as session:
        before = counts(session)
        print("before:", before)
        for stmt in CONSTRAINTS:
            session.run(stmt).consume()
        try:
            session.run(PAID_CONSTRAINT).consume()
        except Exception as exc:                      # older Neo4j: MERGE still works, just slower
            print("note: relationship constraint not created:", str(exc).splitlines()[0])
        print("constraints created")

        load(session, LOAD_CUSTOMERS, cust, "Customer")
        load(session, LOAD_DEVICES, dev, "Device")
        load(session, LOAD_MERCHANTS, mer, "Merchant")
        load(session, LOAD_USED_DEVICE, used, "USED_DEVICE")
        load(session, LOAD_PAID, paid, "PAID")

        after = counts(session)
        print("after: ", after)
        if after == before:
            print("Same counts as before: running this script again created no duplicates.")
    driver.close()


if __name__ == "__main__":
    main()

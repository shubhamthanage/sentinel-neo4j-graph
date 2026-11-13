"""Step 3: three Cypher queries that find patterns that are hard to see in tables."""
from config import NEO4J_DATABASE, get_driver

# ---- Query 1: devices used by 3 or more different customers within 7 days -------------------
# For every payment on a device, look 7 days forward and count the distinct customers.
SHARED_DEVICES = """
MATCH (c:Customer)-[p:PAID]->(:Merchant)
WHERE p.device_id IS NOT NULL
WITH p.device_id AS device_id, collect({customer: c.customer_id, t: p.time}) AS events
UNWIND events AS anchor
WITH device_id, events, anchor.t AS window_start
WITH device_id, window_start,
     [e IN events WHERE e.t >= window_start AND e.t < window_start + duration({days: 7}) | e.customer] AS in_window
UNWIND in_window AS customer
WITH device_id, window_start, collect(DISTINCT customer) AS customers
WHERE size(customers) >= 3
WITH device_id, max(size(customers)) AS customers_in_7_days
MATCH (:Customer)-[p:PAID]->(:Merchant)
WHERE p.device_id = device_id
RETURN device_id, customers_in_7_days, count(p) AS payments, sum(p.fraud_label) AS fraud_payments
ORDER BY fraud_payments DESC, customers_in_7_days DESC, device_id
"""

# ---- Query 2: customers within 2 hops of a fraud-labelled payment ---------------------------
# fraud customer -[USED_DEVICE]-> device <-[USED_DEVICE]- other customer   (2 hops)
NEAR_FRAUD = """
MATCH (f:Customer)-[:PAID {fraud_label: 1}]->(:Merchant)
WITH DISTINCT f
MATCH (f)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Customer)
WHERE other <> f
RETURN other.customer_id AS customer,
       count(DISTINCT f) AS fraud_customers_nearby,
       collect(DISTINCT d.device_id)[0..3] AS via_devices
ORDER BY fraud_customers_nearby DESC, customer
LIMIT 15
"""

# ---- Query 3: merchants most often paid from shared devices ---------------------------------
# "Shared device" = the devices found by Query 1.
MERCHANTS_FROM_SHARED = """
CALL {
""" + SHARED_DEVICES.replace("ORDER BY fraud_payments DESC, customers_in_7_days DESC, device_id", "").replace(
    "RETURN device_id, customers_in_7_days, count(p) AS payments, sum(p.fraud_label) AS fraud_payments",
    "RETURN DISTINCT device_id") + """
}
WITH collect(device_id) AS shared_ids
MATCH (:Customer)-[p:PAID]->(m:Merchant)
WHERE p.device_id IN shared_ids
RETURN m.merchant_id AS merchant, m.category AS category, m.city AS city,
       count(p) AS payments_from_shared_devices,
       count(DISTINCT p.device_id) AS shared_devices_used,
       sum(p.fraud_label) AS fraud_payments
ORDER BY payments_from_shared_devices DESC, merchant
LIMIT 10
"""

CLUSTER_VIEW = """MATCH (d:Device {{device_id: '{device}'}})<-[u:USED_DEVICE]-(c:Customer)
OPTIONAL MATCH (c)-[p:PAID]->(m:Merchant) WHERE p.device_id = d.device_id
RETURN d, u, c, p, m"""


def show(title, rows):
    print(f"\n=== {title} ===")
    if not rows:
        print("(no rows)")
        return
    cols = list(rows[0].keys())
    print("  ".join(f"{c:<22}" for c in cols))
    for r in rows:
        print("  ".join(f"{str(r[c])[:22]:<22}" for c in cols))


def main():
    driver = get_driver()
    driver.verify_connectivity()
    with driver.session(database=NEO4J_DATABASE) as s:
        q1 = [r.data() for r in s.run(SHARED_DEVICES)]
        show("Q1: devices used by 3+ customers within 7 days", q1)
        show("Q2: customers within 2 hops of a fraud-labelled payment (top 15)",
             [r.data() for r in s.run(NEAR_FRAUD)])
        show("Q3: merchants most often paid from shared devices (top 10)",
             [r.data() for r in s.run(MERCHANTS_FROM_SHARED)])
    driver.close()

    if q1:
        worst = q1[0]["device_id"]
        print("\nPaste this into Neo4j Browser (http://localhost:7474) for the graph view of the most suspicious cluster:\n")
        print(CLUSTER_VIEW.format(device=worst))


if __name__ == "__main__":
    main()

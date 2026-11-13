// All Cypher used in 03_queries.py, ready to paste into Neo4j Browser (http://localhost:7474).

// Q1: devices used by 3 or more customers within 7 days
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
ORDER BY fraud_payments DESC, customers_in_7_days DESC, device_id;

// Q2: customers within 2 hops of a fraud-labelled payment
MATCH (f:Customer)-[:PAID {fraud_label: 1}]->(:Merchant)
WITH DISTINCT f
MATCH (f)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Customer)
WHERE other <> f
RETURN other.customer_id AS customer,
       count(DISTINCT f) AS fraud_customers_nearby,
       collect(DISTINCT d.device_id)[0..3] AS via_devices
ORDER BY fraud_customers_nearby DESC, customer
LIMIT 15;

// Q3: merchants most often paid from shared devices ("shared device" = the devices found by Q1)
CALL {
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
  RETURN DISTINCT device_id
}
WITH collect(device_id) AS shared_ids
MATCH (:Customer)-[p:PAID]->(m:Merchant)
WHERE p.device_id IN shared_ids
RETURN m.merchant_id AS merchant, m.category AS category, m.city AS city,
       count(p) AS payments_from_shared_devices,
       count(DISTINCT p.device_id) AS shared_devices_used,
       sum(p.fraud_label) AS fraud_payments
ORDER BY payments_from_shared_devices DESC, merchant
LIMIT 10;

// Graph view of one suspicious cluster: replace <DEVICE_ID> with the top device from Q1
MATCH (d:Device {device_id: '<DEVICE_ID>'})<-[u:USED_DEVICE]-(c:Customer)
OPTIONAL MATCH (c)-[p:PAID]->(m:Merchant) WHERE p.device_id = d.device_id
RETURN d, u, c, p, m;

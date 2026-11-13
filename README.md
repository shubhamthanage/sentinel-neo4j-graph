# SENTINEL fraud graph in Neo4j (Python driver)

Week task 2 - Super30. Fraud often hides in **relationships**: one device used by many customers, or a customer
who is only two hops away from a fraud-labelled payment. A table makes those links hard to see. In a graph they are one query.
This repo loads PayVista SENTINEL entities into Neo4j and finds those patterns with Cypher.

## What is in this repo

| File | What it does |
|---|---|
| `docker-compose.yml` | Runs Neo4j 5 Community locally in Docker on ports 7474 (browser) and 7687 (Bolt) |
| `.env.example` | Template for the settings. Copy it to `.env` (the real `.env` is git-ignored) |
| `config.py` | Reads settings from `.env`, creates the Neo4j driver |
| `graph_data.py` | Reads the SENTINEL kit tables and builds the rows to load (no database code) |
| `01_connect.py` | Connects with the `neo4j` driver, calls `verify_connectivity()`, prints server version and node count |
| `02_load_graph.py` | Creates uniqueness constraints and loads nodes and relationships with `MERGE` |
| `03_queries.py` | Runs the three Cypher queries, prints a text summary of the most suspicious cluster and the Cypher for its graph view |
| `queries.cypher` | The same Cypher (Q1, Q2, Q3, the cluster view and the cluster summaries), ready to paste into Neo4j Browser |
| `03_queries_output.txt` | Full text output of `python 03_queries.py` from my run (Q1-Q3 and the cluster summary) |
| `requirements.txt` | Python packages: `neo4j`, `python-dotenv`, `pandas` |
| `screenshots/` | Output of every step from my run |

Not committed (see `.gitignore`): `.env`, the instructor's `supabase_db_kit/` data and the `neo4j_data/` Docker volume.

## Setup

### 1. Get the code and install
```bash
git clone https://github.com/shubhamthanage/sentinel-neo4j-graph.git
cd sentinel-neo4j-graph
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add your settings
```bash
cp .env.example .env
```
Then edit `.env` and set a real `NEO4J_PASSWORD` (at least 8 characters). The settings are:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-me-please
NEO4J_DATABASE=neo4j
DATA_DIR=supabase_db_kit/data/tables
TARGET_TXNS=5000
```
`.env` is in `.gitignore`, so passwords are never committed.

### 3. Run Neo4j (choose one)

**A. Local Docker (what I used)**
```bash
docker compose up -d
docker logs neo4j-sentinel      # wait until you see "Started."
```
Open http://localhost:7474 and log in with user `neo4j` and your password. The Python driver uses `bolt://localhost:7687`.
`docker-compose.yml` reads the password from your `.env` (`NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}`), so no password is written
in any committed file. Data is kept in `./neo4j_data`.

**B. Neo4j Aura (free)**
Create an AuraDB Free instance, save the credentials it gives you (shown once), then in `.env` set
`NEO4J_URI=neo4j+s://<your-instance-id>.databases.neo4j.io` and the password. This project loads 3,027 nodes and
46,899 relationships, well inside the free limits.

### 4. Data
The data is the SENTINEL **supabase_db_kit** from the instructor (110,000 transactions, 2,500 customers, 200 merchants,
10,120 devices, all synthetic). It is the same data that `python ingest.py all` loads into Supabase; here I read its
`data/tables/*.csv.gz` files directly. Tables used: `transactions`, `labels` (holds `fraud_label`, joined on `transaction_id`),
`customers`, `devices` and `merchants`.

Unzip the kit **inside** this folder, so you have:
```
sentinel-neo4j-graph/
  supabase_db_kit/data/tables/   <- instructor's kit (git-ignored, not part of this repo)
  01_connect.py
  ...
```
Then `DATA_DIR=supabase_db_kit/data/tables` works as it is. If you keep the kit somewhere else, point `DATA_DIR` at its
`data/tables` folder.

**Sample size.** The task needs at least 5,000 transactions. `02_load_graph.py` keeps **every customer who shares a device**
with another customer first (a random sample would cut those clusters apart), then adds more customers if needed.
With the default `TARGET_TXNS=5000` this gives **856 customers, 1,971 devices, 200 merchants, 2,906 USED_DEVICE edges and
43,993 payments (477 fraud-labelled)**. Set `TARGET_TXNS=0` to load all 110,000.

## How to run
```bash
python 01_connect.py          # verify_connectivity()
python 02_load_graph.py       # constraints + MERGE load. Run it a second time: 0 new nodes, 0 new relationships
python 03_queries.py          # the three Cypher queries + cluster summary + the cluster query for the graph view
```
Optional: `python 02_load_graph.py --dry-run` prepares the data and prints the counts without touching Neo4j.

## Graph model

```mermaid
graph LR
    C((Customer<br/>customer_id, age,<br/>home_city, region)) -- "USED_DEVICE<br/>first_seen, last_seen, txn_count" --> D((Device<br/>device_id, kind))
    C -- "PAID<br/>transaction_id, amount, time,<br/>fraud_label, device_id" --> M((Merchant<br/>merchant_id, category, city))
```

- **Customer, Device, Merchant** are nodes. Each has a uniqueness constraint on its id.
- **USED_DEVICE** links a customer to a device they have paid from, with when they first and last used it and how many payments.
- **PAID** is one payment: customer to merchant, with `amount` (rupees, from `amount_paise / 100`), `time` (a Neo4j datetime)
  and `fraud_label` (0 or 1) on the edge.
- **Why `device_id` is also on the PAID edge:** a payment connects a customer and a merchant, and the device is the context.
  Storing the device id on the edge lets us tie any payment to its device without a three-way relationship, which is what the
  "shared devices" queries need.

## MERGE, not CREATE, and constraints
Every load statement uses `MERGE`, so the same row never creates a second node or edge. Uniqueness constraints back this up:
`customer_id_unique`, `device_id_unique`, `merchant_id_unique`, and `paid_txn_unique` on `PAID.transaction_id`
(a relationship constraint, Neo4j 5.7+; on older versions the script prints a note and continues). Loads run in batches of 2,000 rows.

Run `02_load_graph.py` twice: the second run prints `new nodes: 0   new relationships: 0` for every step, the before and after
counts are the same, and it ends with `Same counts as before: running this script again created no duplicates.`

## The three questions (Cypher in `03_queries.py` and `queries.cypher`)

1. **Devices shared by 3 or more customers in 7 days.** For every payment on a device, look 7 days forward and count distinct customers.
2. **Customers within 2 hops of a fraud-labelled payment.** `fraud customer -[USED_DEVICE]-> device <-[USED_DEVICE]- other customer`.
   I follow device links only: following merchants too would reach almost everyone, because the 200 merchants are shared by all customers.
3. **Merchants most often paid from shared devices.** "Shared devices" are the devices found by question 1.

### Results from my run
These are the numbers in `screenshots/03_queries.png`. I also checked them with pandas on the same data.

**Question 1:** 8 devices, each with 3 customers inside a 7-day window. Together they carry 707 payments and 37 fraud-labelled
ones (5.2%, against 1.1% across the loaded payments and 0.6% across all 110,000).

| device_id | customers_in_7_days | payments | fraud_payments |
|---|---|---|---|
| D_c48c331b4ed19bce | 3 | 118 | 8 |
| D_4637ef8d9571a89a | 3 | 79 | 6 |
| D_fd8b0f414ced6d12 | 3 | 74 | 5 |
| D_184ed5721b197852 | 3 | 99 | 4 |
| D_89ec043739e82c62 | 3 | 91 | 4 |
| D_bbaf46afe6619750 | 3 | 109 | 4 |
| D_0c947fb45bb50e72 | 3 | 64 | 3 |
| D_cef59fb95c10c54b | 3 | 73 | 3 |

**Question 2 (top 5 of 15):**

| customer | fraud_customers_nearby | first via device |
|---|---|---|
| C_8403fb2e903349ff | 29 | D_443c9fdd18680358 |
| C_beca2cef67a57db4 | 25 | D_26be10b1819a5412 |
| C_c25537057bf5eab7 | 22 | D_39fd49b9f5ab24e8 |
| C_e5e80f775c861dae | 20 | D_39fd49b9f5ab24e8 |
| C_54f34f5ba61f0d0b | 18 | D_ac17d1f10ed3ab06 |

**Question 3:** 50 merchants receive payments from the 8 shared devices. Top 4:

| merchant | category | city | payments_from_shared_devices | shared_devices_used | fraud_payments |
|---|---|---|---|---|---|
| M_73fa75978cd80349 | electronics | Delhi | 44 | 4 | 5 |
| M_8a78374d3977a8f1 | electronics | Bengaluru | 33 | 3 | 1 |
| M_49967ebb50bb79c3 | gaming | Chennai | 31 | 3 | 3 |
| M_8094417e158fefdb | electronics | Indore | 26 | 3 | 0 |

## One suspicious cluster: device `D_c48c331b4ed19bce`
The top device from question 1. `03_queries.py` prints three text summaries of this cluster (totals, customers, merchants)
and then a ready-to-paste Cypher for the graph view in Neo4j Browser (http://localhost:7474):
```cypher
MATCH (d:Device {device_id: 'D_c48c331b4ed19bce'})<-[u:USED_DEVICE]-(c:Customer)
OPTIONAL MATCH (c)-[p:PAID]->(m:Merchant) WHERE p.device_id = d.device_id
RETURN d, u, c, p, m
```
It returns 118 records (one per payment made from this device). In the Graph view that is **29 nodes (1 Device, 16 Customers,
12 Merchants) and 134 relationships (16 USED_DEVICE, 118 PAID)**.

### Graph view (Neo4j Browser)
![cluster graph view](screenshots/05_cluster_graph.png)

### The same cluster as a diagram
Drawn from the query result (`CLUSTER_VIEW` in `03_queries.py`). Red customers made at least one fraud-labelled payment from this
device; each arrow to a merchant shows how many payments that customer made there from this device.

```mermaid
graph LR
    D{{"Device<br/>D_c48c331b4ed19bce"}}
    C_60b8cec4a71a0882(("C_60b8cec4a71a0882")) -- USED_DEVICE --> D
    C_1eee836953b656c1(("C_1eee836953b656c1")) -- USED_DEVICE --> D
    C_b87f19ade24d3bb4(("C_b87f19ade24d3bb4")) -- USED_DEVICE --> D
    C_cd97879377498ce6(("C_cd97879377498ce6")) -- USED_DEVICE --> D
    C_7b4d24c2b0433a28(("C_7b4d24c2b0433a28")) -- USED_DEVICE --> D
    C_7401fb0078f9b1e2(("C_7401fb0078f9b1e2")) -- USED_DEVICE --> D
    C_a3fef1d1bb96c6fe(("C_a3fef1d1bb96c6fe")) -- USED_DEVICE --> D
    C_2bd85847476a6871(("C_2bd85847476a6871")) -- USED_DEVICE --> D
    C_5bc1f3093ad18d0b(("C_5bc1f3093ad18d0b")) -- USED_DEVICE --> D
    C_bdd6461943c0286f(("C_bdd6461943c0286f")) -- USED_DEVICE --> D
    C_549a1aa6bff02be4(("C_549a1aa6bff02be4")) -- USED_DEVICE --> D
    C_d42ce3705aa17c25(("C_d42ce3705aa17c25")) -- USED_DEVICE --> D
    C_ef9ffbb4eee94ac8(("C_ef9ffbb4eee94ac8")) -- USED_DEVICE --> D
    C_1da562eedfe64e14(("C_1da562eedfe64e14")) -- USED_DEVICE --> D
    C_aee76b01402adacf(("C_aee76b01402adacf")) -- USED_DEVICE --> D
    C_31b398af779a1a10(("C_31b398af779a1a10")) -- USED_DEVICE --> D
    M_1457a882f7587855["M_1457a882f7587855<br/>gift_cards, Bengaluru"]
    M_348a9e09345c7477["M_348a9e09345c7477<br/>electronics, Kolkata"]
    M_5f9ec56b007734f2["M_5f9ec56b007734f2<br/>gift_cards, Hyderabad"]
    M_5fde3bb6a98424ab["M_5fde3bb6a98424ab<br/>gift_cards, Ahmedabad"]
    M_705380854377bd52["M_705380854377bd52<br/>gaming, Bhubaneswar"]
    M_73fa75978cd80349["M_73fa75978cd80349<br/>electronics, Delhi"]
    M_8613b75179e11c81["M_8613b75179e11c81<br/>gaming, Pune"]
    M_8a78374d3977a8f1["M_8a78374d3977a8f1<br/>electronics, Bengaluru"]
    M_922e1ba1d4d04ff2["M_922e1ba1d4d04ff2<br/>electronics, Hyderabad"]
    M_ce0b45ab7127ca6a["M_ce0b45ab7127ca6a<br/>electronics, Indore"]
    M_f5086339052622fa["M_f5086339052622fa<br/>gaming, Jamshedpur"]
    M_fc112fe3be63f797["M_fc112fe3be63f797<br/>gaming, Pune"]
    C_60b8cec4a71a0882 -- "PAID x7" --> M_1457a882f7587855
    C_1eee836953b656c1 -- "PAID x5, 1 fraud" --> M_348a9e09345c7477
    C_b87f19ade24d3bb4 -- "PAID x9" --> M_348a9e09345c7477
    C_cd97879377498ce6 -- "PAID x9, 1 fraud" --> M_5f9ec56b007734f2
    C_7b4d24c2b0433a28 -- "PAID x6" --> M_5fde3bb6a98424ab
    C_7401fb0078f9b1e2 -- "PAID x6, 1 fraud" --> M_705380854377bd52
    C_a3fef1d1bb96c6fe -- "PAID x8, 1 fraud" --> M_73fa75978cd80349
    C_2bd85847476a6871 -- "PAID x7, 1 fraud" --> M_8613b75179e11c81
    C_5bc1f3093ad18d0b -- "PAID x9" --> M_8613b75179e11c81
    C_bdd6461943c0286f -- "PAID x9" --> M_8a78374d3977a8f1
    C_549a1aa6bff02be4 -- "PAID x9" --> M_922e1ba1d4d04ff2
    C_d42ce3705aa17c25 -- "PAID x6, 1 fraud" --> M_ce0b45ab7127ca6a
    C_ef9ffbb4eee94ac8 -- "PAID x7, 1 fraud" --> M_ce0b45ab7127ca6a
    C_1da562eedfe64e14 -- "PAID x5" --> M_f5086339052622fa
    C_aee76b01402adacf -- "PAID x9, 1 fraud" --> M_f5086339052622fa
    C_31b398af779a1a10 -- "PAID x7" --> M_fc112fe3be63f797
    classDef fraud fill:#f8d7da,stroke:#c0392b,color:#000
    classDef dev fill:#cfe2ff,stroke:#0d6efd,color:#000
    classDef merch fill:#ffe5b4,stroke:#e67e22,color:#000
    class C_1eee836953b656c1,C_2bd85847476a6871,C_7401fb0078f9b1e2,C_a3fef1d1bb96c6fe,C_aee76b01402adacf,C_cd97879377498ce6,C_d42ce3705aa17c25,C_ef9ffbb4eee94ac8 fraud
    class D dev
    class M_1457a882f7587855,M_348a9e09345c7477,M_5f9ec56b007734f2,M_5fde3bb6a98424ab,M_705380854377bd52,M_73fa75978cd80349,M_8613b75179e11c81,M_8a78374d3977a8f1,M_922e1ba1d4d04ff2,M_ce0b45ab7127ca6a,M_f5086339052622fa,M_fc112fe3be63f797 merch
```

### The same cluster as query output
`03_queries.py` output from my run (queries `CLUSTER_TOTALS`, `CLUSTER_CUSTOMERS`, `CLUSTER_MERCHANTS`; full output in `03_queries_output.txt`):

**Totals**

| customers | merchants | used_device_edges | paid_edges | fraud_payments |
|---|---|---|---|---|
| 16 | 12 | 16 | 118 | 8 |

**Customers who used this device**

| customer | first_seen | last_seen | payments | merchants | fraud_payments |
|---|---|---|---|---|---|
| C_aee76b01402adacf | 2025-08-23 | 2025-08-23 | 9 | 1 | 1 |
| C_cd97879377498ce6 | 2025-04-09 | 2025-04-09 | 9 | 1 | 1 |
| C_a3fef1d1bb96c6fe | 2025-02-26 | 2025-02-26 | 8 | 1 | 1 |
| C_2bd85847476a6871 | 2025-02-26 | 2025-02-26 | 7 | 1 | 1 |
| C_ef9ffbb4eee94ac8 | 2025-01-03 | 2025-01-03 | 7 | 1 | 1 |
| C_7401fb0078f9b1e2 | 2025-06-28 | 2025-06-28 | 6 | 1 | 1 |
| C_d42ce3705aa17c25 | 2024-12-11 | 2024-12-11 | 6 | 1 | 1 |
| C_1eee836953b656c1 | 2025-04-09 | 2025-04-09 | 5 | 1 | 1 |
| C_549a1aa6bff02be4 | 2025-09-07 | 2025-09-07 | 9 | 1 | 0 |
| C_5bc1f3093ad18d0b | 2025-10-01 | 2025-10-01 | 9 | 1 | 0 |
| C_b87f19ade24d3bb4 | 2025-08-15 | 2025-08-15 | 9 | 1 | 0 |
| C_bdd6461943c0286f | 2026-02-13 | 2026-02-13 | 9 | 1 | 0 |
| C_31b398af779a1a10 | 2025-02-21 | 2025-02-21 | 7 | 1 | 0 |
| C_60b8cec4a71a0882 | 2025-09-14 | 2025-09-14 | 7 | 1 | 0 |
| C_7b4d24c2b0433a28 | 2025-09-15 | 2025-09-15 | 6 | 1 | 0 |
| C_1da562eedfe64e14 | 2025-03-05 | 2025-03-05 | 5 | 1 | 0 |

**Merchants paid from this device**

| merchant | category | city | payments | customers | fraud_payments |
|---|---|---|---|---|---|
| M_8613b75179e11c81 | gaming | Pune | 16 | 2 | 1 |
| M_348a9e09345c7477 | electronics | Kolkata | 14 | 2 | 1 |
| M_f5086339052622fa | gaming | Jamshedpur | 14 | 2 | 1 |
| M_ce0b45ab7127ca6a | electronics | Indore | 13 | 2 | 2 |
| M_5f9ec56b007734f2 | gift_cards | Hyderabad | 9 | 1 | 1 |
| M_8a78374d3977a8f1 | electronics | Bengaluru | 9 | 1 | 0 |
| M_922e1ba1d4d04ff2 | electronics | Hyderabad | 9 | 1 | 0 |
| M_73fa75978cd80349 | electronics | Delhi | 8 | 1 | 1 |
| M_1457a882f7587855 | gift_cards | Bengaluru | 7 | 1 | 0 |
| M_fc112fe3be63f797 | gaming | Pune | 7 | 1 | 0 |
| M_5fde3bb6a98424ab | gift_cards | Ahmedabad | 6 | 1 | 0 |
| M_705380854377bd52 | gaming | Bhubaneswar | 6 | 1 | 1 |

### Why it is suspicious
- **One device, 16 customers.** A normal phone or laptop belongs to one person. Here 16 different customers paid from it, and each
  of them used it on a single day only (`first_seen` = `last_seen`), as if the device is handed from account to account.
- **3 customers inside 7 days.** `C_31b398af779a1a10` (21 Feb 2025), `C_a3fef1d1bb96c6fe` and `C_2bd85847476a6871` (both 26 Feb 2025)
  used it within 5 days of each other. This is why question 1 flags it.
- **High fraud rate.** 8 of its 118 payments are fraud-labelled (6.8%), against 1.1% across all loaded payments and 0.6% across
  the full 110,000. Half of the customers (8 of 16) have a fraud-labelled payment from this device.
- **Easy-to-resell categories.** All 12 merchants are gaming, electronics or gift-card merchants, which are typical cash-out targets.
- **Shared merchants.** 4 merchants (`M_8613b75179e11c81`, `M_348a9e09345c7477`, `M_f5086339052622fa`, `M_ce0b45ab7127ca6a`) were
  paid by 2 different customers from this same device; `M_ce0b45ab7127ca6a` got a fraud payment from both of them.

This looks like a mule or ring device, so the device, its 16 customers and these 12 merchants should be reviewed together.

## Screenshots

**1. Connect** - `01_connect.py`: connected to `bolt://localhost:7687`, Neo4j Kernel 5.26.33 (community), 3,027 nodes.

![connect](screenshots/01_connect.png)

**2. First load** - `02_load_graph.py` on an empty database creates 856 + 1,971 + 200 nodes and 2,906 + 43,993 relationships.

![load](screenshots/02_load.png)

**3. Second load** - the same script again: 0 new nodes and 0 new relationships, counts unchanged.

![load again](screenshots/02_load_second_run.png)

**4. Queries** - `03_queries.py` output for Q1, Q2 and Q3.

![queries](screenshots/03_queries.png)

**5. Constraints** - `SHOW CONSTRAINTS` in Neo4j Browser: three node uniqueness constraints and the `PAID` relationship constraint.

![constraints](screenshots/04_constraints.png)

**6. Cluster graph** - Graph view of the cluster query for `D_c48c331b4ed19bce` in Neo4j Browser: the device (blue) in the centre, the 16 customers (pink) linked to it by USED_DEVICE, and the 12 merchants (orange) they paid from it. 29 nodes, 134 relationships, 118 records.

![cluster](screenshots/05_cluster_graph.png)

## Notes
- Timestamps are stored as Neo4j datetimes (converted from UTC ISO strings with `datetime()` inside Cypher).
- Never commit `.env`. If a password ever leaks, change it in Neo4j (or reset the Aura instance).
- All data is synthetic.

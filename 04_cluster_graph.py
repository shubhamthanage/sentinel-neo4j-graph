"""Step 4: draw the most suspicious cluster as a graph picture (SVG), straight from Neo4j.

Takes the top device from Query 1, reads the same subgraph as the Neo4j Browser graph view
(device <-USED_DEVICE- customers -PAID-> merchants) and writes screenshots/05_cluster_graph.svg.
The SVG is written by hand, so no plotting library is needed.
"""
import importlib
import math
import os
from html import escape

from config import NEO4J_DATABASE, get_driver

queries = importlib.import_module("03_queries")      # reuse SHARED_DEVICES and CLUSTER_* queries

OUT_FILE = os.path.join("screenshots", "05_cluster_graph.svg")

CLUSTER_EDGES = """
MATCH (d:Device {device_id: $device})<-[:USED_DEVICE]-(c:Customer)
OPTIONAL MATCH (c)-[p:PAID]->(m:Merchant) WHERE p.device_id = d.device_id
RETURN c.customer_id AS customer, m.merchant_id AS merchant, m.category AS category, m.city AS city,
       count(p) AS payments, sum(p.fraud_label) AS fraud_payments
ORDER BY merchant, customer
"""

W = H = 1100
CX, CY = W / 2, H / 2 + 20
R_CUSTOMER, R_MERCHANT = 240, 430


def point(radius, angle):
    return CX + radius * math.cos(angle), CY + radius * math.sin(angle)


def draw(device, edges, totals):
    merchants = list(dict.fromkeys(e["merchant"] for e in edges if e["merchant"]))
    m_info = {e["merchant"]: (e["category"], e["city"]) for e in edges if e["merchant"]}

    # customers are spread evenly on the inner ring (grouped by merchant, edges are sorted by merchant);
    # each merchant sits on the outer ring at the average angle of the customers who paid it
    customers = list(dict.fromkeys(e["customer"] for e in edges))
    c_angle = {c: 2 * math.pi * i / len(customers) - math.pi / 2 for i, c in enumerate(customers)}
    c_pos = {c: point(R_CUSTOMER, a) for c, a in c_angle.items()}
    c_fraud = {c: any(e["fraud_payments"] for e in edges if e["customer"] == c) for c in customers}
    m_angle = {}
    for m in merchants:
        angles = [c_angle[e["customer"]] for e in edges if e["merchant"] == m]
        m_angle[m] = math.atan2(sum(map(math.sin, angles)), sum(map(math.cos, angles)))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           'font-family="Helvetica, Arial, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="{W / 2}" y="34" font-size="22" text-anchor="middle" font-weight="bold">'
           f'Suspicious cluster around device {escape(device)}</text>',
           f'<text x="{W / 2}" y="60" font-size="15" text-anchor="middle" fill="#444">'
           f'{totals["customers"]} customers, {totals["merchants"]} merchants, '
           f'{totals["used_device_edges"]} USED_DEVICE + {totals["paid_edges"]} PAID relationships, '
           f'{totals["fraud_payments"]} fraud-labelled payments</text>']

    # edges first, so nodes are drawn on top
    for c, (x, y) in c_pos.items():
        svg.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{CX}" y2="{CY}" stroke="#6c8ebf" stroke-width="1.5"/>')
    for e in edges:
        if not e["merchant"]:
            continue
        (x1, y1), (x2, y2) = c_pos[e["customer"]], point(R_MERCHANT, m_angle[e["merchant"]])
        colour = "#c0392b" if e["fraud_payments"] else "#999999"
        label = f'PAID x{e["payments"]}' + (f', {e["fraud_payments"]} fraud' if e["fraud_payments"] else "")
        svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{colour}" '
                   f'stroke-width="{1 + e["payments"] / 3:.1f}"/>')
        lx, ly = x1 + (x2 - x1) * 0.45, y1 + (y2 - y1) * 0.45
        svg.append(f'<text x="{lx:.1f}" y="{ly - 4:.1f}" font-size="10" '
                   f'text-anchor="middle" fill="{colour}">{label}</text>')

    svg.append(f'<circle cx="{CX}" cy="{CY}" r="46" fill="#cfe2ff" stroke="#0d6efd" stroke-width="3"/>')
    svg.append(f'<text x="{CX}" y="{CY - 4}" font-size="12" text-anchor="middle" font-weight="bold">Device</text>')
    svg.append(f'<text x="{CX}" y="{CY + 12}" font-size="9" text-anchor="middle">{escape(device)}</text>')

    for c, (x, y) in c_pos.items():
        fill, stroke = ("#f8d7da", "#c0392b") if c_fraud[c] else ("#fde2ef", "#d63384")
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="22" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        svg.append(f'<text x="{x:.1f}" y="{y + 34:.1f}" font-size="9" text-anchor="middle">{escape(c)}</text>')

    for m in merchants:
        x, y = point(R_MERCHANT, m_angle[m])
        category, city = m_info[m]
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="30" fill="#ffe5b4" stroke="#e67e22" stroke-width="2"/>')
        svg.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="10" text-anchor="middle">{escape(category)}</text>')
        svg.append(f'<text x="{x:.1f}" y="{y + 44:.1f}" font-size="9" text-anchor="middle">{escape(m)}</text>')
        svg.append(f'<text x="{x:.1f}" y="{y + 56:.1f}" font-size="9" text-anchor="middle" fill="#666">'
                   f'{escape(city)}</text>')

    legend = [("#cfe2ff", "#0d6efd", "Device"), ("#fde2ef", "#d63384", "Customer"),
              ("#f8d7da", "#c0392b", "Customer with a fraud-labelled payment"), ("#ffe5b4", "#e67e22", "Merchant")]
    for i, (fill, stroke, text) in enumerate(legend):
        y = H - 100 + i * 22
        svg.append(f'<circle cx="40" cy="{y}" r="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        svg.append(f'<text x="56" y="{y + 4}" font-size="13">{text}</text>')
    svg.append(f'<text x="{W - 30}" y="{H - 30}" font-size="12" text-anchor="end" fill="#666">'
               'Red edges = PAID with fraud_label = 1; edge width = number of payments</text>')
    svg.append("</svg>")
    return "\n".join(svg)


def main():
    driver = get_driver()
    driver.verify_connectivity()
    with driver.session(database=NEO4J_DATABASE) as s:
        top = s.run(queries.SHARED_DEVICES).data()
        if not top:
            print("Query 1 found no shared devices, nothing to draw.")
            return
        device = top[0]["device_id"]
        totals = s.run(queries.CLUSTER_TOTALS, device=device).single().data()
        edges = s.run(CLUSTER_EDGES, device=device).data()
    driver.close()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(draw(device, edges, totals))
    print(f"device: {device}")
    print(f"nodes: 1 Device + {totals['customers']} Customer + {totals['merchants']} Merchant = "
          f"{1 + totals['customers'] + totals['merchants']}")
    print(f"relationships: {totals['used_device_edges']} USED_DEVICE + {totals['paid_edges']} PAID = "
          f"{totals['used_device_edges'] + totals['paid_edges']}   fraud-labelled payments: {totals['fraud_payments']}")
    print(f"wrote {OUT_FILE}")


if __name__ == "__main__":
    main()

"""Step 1: connect to Neo4j and prove it works (verify_connectivity)."""
from config import NEO4J_DATABASE, NEO4J_URI, get_driver

driver = get_driver()
driver.verify_connectivity()                      # raises an error if Neo4j cannot be reached
print("connected to:", NEO4J_URI)

with driver.session(database=NEO4J_DATABASE) as session:
    record = session.run("CALL dbms.components() YIELD name, versions, edition "
                         "RETURN name, versions[0] AS version, edition").single()
    print(f"server: {record['name']} {record['version']} ({record['edition']})")
    print("nodes in database right now:", session.run("MATCH (n) RETURN count(n) AS n").single()["n"])
driver.close()

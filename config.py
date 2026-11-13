"""Shared settings. Everything secret comes from the .env file, never from code."""
import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
DATA_DIR = os.getenv("DATA_DIR", "supabase_db_kit/data/tables")
TARGET_TXNS = int(os.getenv("TARGET_TXNS", "5000"))


def get_driver():
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        sys.exit("NEO4J_PASSWORD is not set. Copy .env.example to .env and fill it in.")
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, password))

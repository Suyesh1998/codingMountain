# utils.py
import psycopg2
from neo4j import GraphDatabase
import config


class DatabaseConnections:
    """Utility class for managing database connections."""
    
    @staticmethod
    def connect_postgres():
        """Establish PostgreSQL connection with autocommit enabled."""
        conn = psycopg2.connect(
            dbname=config.POSTGRES["dbname"],
            user=config.POSTGRES["user"],
            password=config.POSTGRES["password"],
            host=config.POSTGRES["host"],
            port=config.POSTGRES["port"]
        )
        conn.autocommit = True
        return conn
    
    @staticmethod
    def connect_neo4j():
        """Establish Neo4j connection."""
        return GraphDatabase.driver(
            config.NEO4J["uri"],
            auth=(config.NEO4J["user"], config.NEO4J["password"])
        )
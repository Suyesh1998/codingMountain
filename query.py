# query.py

# ------------------------
# Imports
# ------------------------
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from neo4j import GraphDatabase
import uvicorn

# ------------------------
# Import connections from utils.py
# ------------------------
from utils import DatabaseConnections

connect_postgres = DatabaseConnections.connect_postgres
connect_neo4j = DatabaseConnections.connect_neo4j

# ------------------------
# Placeholder embedding function
# ------------------------
def generate_embedding(text: str):
    # Replace with your actual embedding generation logic
    return [0.0] * 384

# ------------------------
# FastAPI app
# ------------------------
app = FastAPI(title="CTI Search API")

# ------------------------
# Request models
# ------------------------
class HybridSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5
    semantic_weight: Optional[float] = 0.5
    lexical_weight: Optional[float] = None

class IndicatorsByTypeRequest(BaseModel):
    indicator_type: str
    limit: Optional[int] = 25

class IndicatorContextRequest(BaseModel):
    indicator_value: str
    limit: Optional[int] = 5

class RelationshipsRequest(BaseModel):
    indicator_value: str
    hops: Optional[int] = 2
    limit: Optional[int] = 25

# ------------------------
# Hybrid Search (Postgres)
# ------------------------
@app.post("/hybrid_search")
def hybrid_search_api(payload: HybridSearchRequest):
    if payload.lexical_weight is None:
        lexical_weight = 1 - payload.semantic_weight
    else:
        lexical_weight = payload.lexical_weight

    query_embedding = generate_embedding(payload.query)
    conn = connect_postgres()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            """
            SELECT 
                c.uuid AS chunk_uuid,
                c.text,
                d.name AS document_name,
                c.page,
                c.indicators,
                c.language,
                (%s * (1 - (c.embedding <=> %s::vector)) +
                 %s * ts_rank(c.tsv, plainto_tsquery('english', %s))) AS hybrid_score
            FROM pdf.chunks c
            JOIN pdf.documents d ON c.document_uuid = d.uuid
            ORDER BY hybrid_score DESC
            LIMIT %s;
            """,
            (payload.semantic_weight, query_embedding, lexical_weight, payload.query, payload.limit)
        )
        results = [dict(r) for r in cur.fetchall()]
        cur.close()
        return {"results": results}
    finally:
        conn.close()

# ------------------------
# Neo4j: Indicators by type
# ------------------------
@app.post("/indicators_by_type")
def get_indicators_by_type_api(payload: IndicatorsByTypeRequest):
    driver = connect_neo4j()
    try:
        with driver.session() as session:
            cypher = """
            MATCH (n:Indicator)
            WHERE n.type = $type
            RETURN n.value AS indicator
            LIMIT $limit
            """
            result = session.run(cypher, type=payload.indicator_type, limit=payload.limit)
            indicators = [r["indicator"] for r in result]
            return {"indicators": indicators}
    finally:
        driver.close()

# ------------------------
# Neo4j: Indicator context
# ------------------------
@app.post("/indicator_context")
def get_indicator_context_api(payload: IndicatorContextRequest):
    driver = connect_neo4j()
    try:
        with driver.session() as session:
            cypher = """
            MATCH (i:Indicator {value: $value})-[:MENTIONED_IN]->(d:Document)
            RETURN d.name AS document_name, i.value AS indicator, d.created_at AS created_at
            LIMIT $limit
            """
            result = session.run(cypher, value=payload.indicator_value, limit=payload.limit)
            context = [r.data() for r in result]
            return {"context": context}
    finally:
        driver.close()

# ------------------------
# Neo4j: Indicator relationships
# ------------------------
@app.post("/indicator_relationships")
def get_indicator_relationships_api(payload: RelationshipsRequest):
    driver = connect_neo4j()
    try:
        cypher_query = f"""
        MATCH (i:Indicator {{value: $indicator}})-[r*1..{payload.hops}]-(connected)
        UNWIND r AS rel
        RETURN DISTINCT 
               i.value AS indicator,
               type(rel) AS relationship,
               connected.value AS connected_node,
               labels(connected) AS connected_labels,
               CASE WHEN startNode(rel) = i THEN 'outgoing' ELSE 'incoming' END AS direction
        LIMIT $limit
        """
        with driver.session() as session:
            result = session.run(cypher_query, indicator=payload.indicator_value, limit=payload.limit)
            relationships = [record.data() for record in result]
            return {"relationships": relationships}
    finally:
        driver.close()

# ------------------------
# Run API (Terminal Mode)
# ------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8013, log_level="info")

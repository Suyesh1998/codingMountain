# Threat Intelligence Document Processing Pipeline

A comprehensive cybersecurity threat intelligence (CTI) processing system that extracts, analyzes, and stores threat indicators from PDF documents using PostgreSQL for semantic search and Neo4j for relationship mapping.

## Overview

This system processes threat intelligence reports to extract both structured indicators and unstructured content, implementing a hybrid approach combining relational database storage with graph-based relationship analysis.

### Processed Documents
- Operation Overload
- Storm-1516 Technical Report  
- Doppelgänger Campaign Report

## Architecture

### Data Storage Strategy (Hybrid Approach)
- **PostgreSQL**: Document storage, semantic search, structured queries
- **Neo4j**: Graph relationships, pattern detection, network analysis
- **Vector Store**: pgvector extension for semantic similarity search

### Processing Pipeline
```
PDF Documents → Text Extraction → Language Detection → Smart Chunking → 
Indicator Extraction → Embedding Generation → Dual Database Storage
```

## Features

### Document Processing & Embedding
- **PDF Extraction**: Multi-column layout handling with PyMuPDF
- **Smart Chunking**: SpaCy-based semantic chunking with recursive fallback
- **Multi-language Support**: English, French, German with language-specific processing
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2 for multilingual content

### Indicator Extraction
Automatically detects and normalizes:
- **Domains**: example.com
- **URLs**: https://...
- **IP Addresses**: IPv4 validation
- **Email Addresses**: Normalized to lowercase
- **Phone Numbers**: International format (E164)
- **Social Media Handles**: @username patterns
- **Tracking IDs**: Google Analytics (UA-...), AdSense (Pub-...)

### Query Capabilities
- **Hybrid Search**: Vector similarity + full-text search
- **Graph Traversal**: Multi-hop relationship queries
- **Indicator Lookup**: Type-based filtering
- **Context Retrieval**: Source document mapping

## Installation

### Prerequisites
- Python 3.12+
- PostgreSQL 12+ with pgvector extension
- Neo4j 4.4+

#### 1. Python Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

#### 2. SpaCy Models
```bash
python -m spacy download en_core_web_sm
python -m spacy download fr_core_news_sm
python -m spacy download de_core_news_sm
```

#### 3. PostgreSQL Setup
```sql
CREATE DATABASE threatintel;
CREATE USER cti_user WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE threatintel TO cti_user;

\c threatintel;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA pdf;

-- Documents table
CREATE TABLE pdf.documents (
    uuid UUID PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT,
    language TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Chunks table with vector embeddings
CREATE TABLE pdf.chunks (
    uuid UUID PRIMARY KEY,
    document_uuid UUID REFERENCES pdf.documents(uuid),
    text TEXT NOT NULL,
    embedding vector(384),
    indicators TEXT[],
    page INTEGER,
    language TEXT,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_chunks_embedding ON pdf.chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_tsv ON pdf.chunks USING gin(tsv);
```

#### 4. Neo4j Setup
Ensure Neo4j is running and accessible. The application automatically creates the graph schema.

## Configuration

Create `.env` file:
```env
# PostgreSQL
POSTGRES_DB=threatintel
POSTGRES_USER=cti_user
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# Processing
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
REGIONS=US,NP,FR,DE
```

### Processing Configuration (config.py)
```python
CHUNK_SIZE = 500          # Maximum characters per chunk
CHUNK_OVERLAP = 200       # Character overlap between chunks
MAX_PAGES = 100          # Maximum pages per PDF
```

## Usage

### Directory Structure
Ensure your project structure matches:
```
project/
├── main.py               # Main preprocessing script
├── query.py              # API server
├── config.py             # Configuration
├── utils.py              # Database utilities
├── preprocessing.py      # Processing pipeline
├── pdfs/                 # Place your PDF files here
│   ├── Operation_Overload.pdf
│   ├── Storm-1516 Technical Report.pdf
│   └── DoppelgÃ¤nger Campaign Report.pdf
├── clean/               # Generated clean text files
├── raw/                 # Generated indicator JSON files
└── .env                 # Environment configuration
```

## Running the Project

### Step 1: Data Preprocessing
First, run the preprocessing pipeline to extract and process PDF documents:

```bash
python main.py
```

This will:
- Process all PDFs in the `pdfs/` directory
- Extract text from Operation_Overload, Storm-1516 Technical Report, and Doppelganger Campaign Report
- Generate 384-dimensional embeddings using sentence-transformers
- Extract indicators (domains, IPs, emails, URLs, social handles, tracking IDs)
- Store processed data in PostgreSQL and Neo4j databases
- Create clean text files in `clean/` directory
- Generate indicator JSON files in `raw/` directory

**Expected Output:**
```
📄 Processing: Operation_Overload
📄 Created 422 chunks for Operation_Overload
✅ Neo4j connection successful
💾 Saved clean text -> .../clean/Operation_Overload_clean.txt
💾 Saved indicators -> .../raw/Operation_Overload_indicators.json
✅ Processed 'Operation_Overload' (422 chunks, 90 pages)
...
📊 Processing complete: 3/3 PDFs processed successfully
```

### Step 2: Start the Query API
After preprocessing is complete, start the API server:

```bash
python query.py
```

This will start the FastAPI server on `http://127.0.0.1:8013` for querying the processed data.

**API Server Output:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8013 (Press CTRL+C to quit)
```

API available at: `http://127.0.0.1:8013`  

## API Endpoints

### Hybrid Search
**POST** `/hybrid_search`

Combines semantic vector similarity with PostgreSQL full-text search for comprehensive document retrieval.

**Parameters:**
- `query` (string, required): Search query text
- `limit` (integer, optional): Maximum results to return (default: 5, max: 100)
- `semantic_weight` (float, optional): Weight for vector similarity (0.0-1.0, default: 0.5)
- `lexical_weight` (float, optional): Weight for full-text search (auto-calculated if not provided)

**Example Request:**
```json
{
  "query": "Russian disinformation campaigns targeting France",
  "limit": 10,
  "semantic_weight": 0.7,
  "lexical_weight": 0.3
}
```

**Response:**
```json
{
  "results": [
    {
      "chunk_uuid": "abc123...",
      "text": "Content excerpt...",
      "document_name": "Doppelgänger Campaign Report",
      "page": 15,
      "indicators": ["domain1.com", "192.168.1.1"],
      "language": "en",
      "hybrid_score": 0.85
    }
  ]
}
```

### Indicators by Type
**POST** `/indicators_by_type`

Retrieve all indicators of a specific type from the Neo4j graph database.

**Parameters:**
- `indicator_type` (string, required): Type of indicators to retrieve
  - Valid types: `domains`, `urls`, `ips`, `emails`, `phones`, `social_handles`, `tracking_ids`
- `limit` (integer, optional): Maximum indicators to return (default: 25, max: 1000)

**Example Request:**
```json
{
  "indicator_type": "domains",
  "limit": 50
}
```

**Response:**
```json
{
  "indicators": [
    "malicious-domain.com",
    "suspicious-site.org",
    "threat-actor.net"
  ]
}
```

### Indicator Context
**POST** `/indicator_context`

Find all documents where a specific indicator is mentioned with contextual information.

**Parameters:**
- `indicator_value` (string, required): Exact indicator value to search for
- `limit` (integer, optional): Maximum context entries to return (default: 5, max: 100)

**Example Request:**
```json
{
  "indicator_value": "malicious-domain.com",
  "limit": 10
}
```

**Response:**
```json
{
  "context": [
    {
      "document_name": "Storm-1516 Technical Report",
      "indicator": "malicious-domain.com",
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "document_name": "Operation Overload",
      "indicator": "malicious-domain.com", 
      "created_at": "2024-01-12T08:45:00Z"
    }
  ]
}
```

### Indicator Relationships
**POST** `/indicator_relationships`

Perform graph traversal to find indicators connected to a given indicator within specified hops.

**Parameters:**
- `indicator_value` (string, required): Starting indicator for graph traversal
- `hops` (integer, optional): Maximum relationship hops to traverse (default: 2, max: 5)
- `limit` (integer, optional): Maximum relationships to return (default: 25, max: 500)

**Example Request:**
```json
{
  "indicator_value": "192.168.1.1",
  "hops": 3,
  "limit": 100
}
```

**Response:**
```json
{
  "relationships": [
    {
      "indicator": "192.168.1.1",
      "relationship": "MENTIONED_IN",
      "connected_node": "Storm-1516 Technical Report",
      "connected_labels": ["Document"],
      "direction": "outgoing"
    },
    {
      "indicator": "192.168.1.1",
      "relationship": "RELATED_TO",
      "connected_node": "suspicious-domain.com",
      "connected_labels": ["Indicator"],
      "direction": "incoming"
    }
  ]
}
```

### API Response Codes

- **200 OK**: Successful request with results
- **400 Bad Request**: Invalid parameters or malformed request
- **404 Not Found**: No results found for query
- **422 Unprocessable Entity**: Validation error in request parameters
- **500 Internal Server Error**: Database connection or processing error

### Rate Limiting and Performance

- API endpoints are optimized for sub-second response times
- Concurrent requests are supported with connection pooling
- Large result sets are automatically paginated
- Vector similarity searches use efficient ivfflat indexing

## Test Queries Implementation

### 1. Semantic Search
```python
# "What Russian disinformation campaigns target France?"
response = requests.post("/hybrid_search", json={
    "query": "Russian disinformation campaigns France",
    "semantic_weight": 0.8
})
```

### 2. Indicator Lookup
```python
# "Find all domains associated with Doppelgänger"
response = requests.post("/hybrid_search", json={
    "query": "Doppelgänger domains",
    "limit": 50
})
```

### 3. Graph Traversal
```python
# "Show all indicators within 2 hops of domain X"
response = requests.post("/indicator_relationships", json={
    "indicator_value": "example.com",
    "hops": 2,
    "limit": 100
})
```


## Architecture Diagram

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   PDF Files     │───▶│  Processing      │───▶│   PostgreSQL    │
│                 │    │   Pipeline       │    │  (Documents +   │
└─────────────────┘    │                  │    │   Embeddings)   │
                       │  - Text Extract  │    └─────────────────┘
┌─────────────────┐    │  - Chunking      │           │
│   SpaCy Models  │───▶│  - Indicators    │           │
└─────────────────┘    │  - Embeddings    │           ▼
                       └──────────────────┘    ┌─────────────────┐
┌─────────────────┐                           │     Neo4j       │
│ Sentence Trans. │──────────────────────────▶│ (Relationships) │
└─────────────────┘                           └─────────────────┘
                                                       │
                       ┌──────────────────┐           │
                       │   FastAPI        │◀──────────┘
                       │     Server       │
                       └──────────────────┘
```

## Data Model

### PostgreSQL Schema
```sql
pdf.documents (uuid, name, path, language, created_at)
pdf.chunks (uuid, document_uuid, text, embedding, indicators[], page, language, tsv)
```

### Neo4j Schema
```cypher
(:Document {uuid, name, path, language, created_at})
(:Indicator {uuid, value, type, created_at})
(:Indicator)-[:MENTIONED_IN {page, category}]->(:Document)
```



## Development

### Project Structure
```
├── config.py              # Configuration management
├── utils.py               # Database connections
├── preprocessing.py       # Core processing pipeline
├── query.py              # FastAPI server
├── main.py               # Processing execution
├── requirements.txt      # Python dependencies
├── pdfs/                 # Input documents
├── clean/               # Processed text output
└── raw/                 # Extracted indicators JSON
```



## Troubleshooting

### Common Issues

1. **SpaCy Model Missing**: Install required language models
2. **pgvector Extension**: Ensure extension is enabled in PostgreSQL
3. **Neo4j Connection**: Verify credentials and network connectivity
4. **Memory Issues**: Adjust chunk size for large documents




## License

MIT License - see LICENSE file for details
# preprocessing.py
import fitz  # PyMuPDF
import re
import ipaddress
import phonenumbers
import json
import uuid
from pathlib import Path
from langdetect import detect, DetectorFactory
from langchain.text_splitter import SpacyTextSplitter, RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import config

DetectorFactory.seed = 0  # deterministic language detection


# -------------------------
# EMBEDDING SERVICE
# Handles text-to-vector conversion using SentenceTransformers
# Used for generating embeddings that will be stored in PostgreSQL for semantic search
# -------------------------
class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self):
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    
    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for given text."""
        return self.model.encode(text).tolist()


# -------------------------
# PDF EXTRACTOR
# Handles the core PDF reading functionality using PyMuPDF (fitz)
# Extracts text content page by page with configurable page limits
# -------------------------
class PDFExtractor:
    """Handles PDF text extraction operations."""
    
    @staticmethod
    def extract_text_from_pdf(pdf_path):
        """Extract text from PDF with page limit."""
        doc = fitz.open(pdf_path)
        text_data = []
        for page_num, page in enumerate(doc, start=1):
            if page_num > config.MAX_PAGES:
                break
            text_data.append({"page": page_num, "text": page.get_text("text")})
        doc.close()
        return text_data


# -------------------------
# TEXT PROCESSOR
# Handles all text manipulation tasks: cleaning, language detection, and chunking
# Uses multiple strategies for chunking (SpaCy + fallback to RecursiveCharacterTextSplitter)
# Supports multiple languages (EN, FR, DE) with appropriate NLP pipelines
# -------------------------
class TextProcessor:
    """Handles text cleaning, language detection, and chunking."""
    
    @staticmethod
    def clean_text(text):
        """Clean and normalize text."""
        text = re.sub(r"\s+", " ", text)
        text = text.replace(""", "\"").replace(""", "\"").replace("'", "'").replace("–", "-")
        return text.strip()
    
    @staticmethod
    def detect_language(text):
        """Detect language of text with fallback to English."""
        try:
            lang = detect(text)
            if lang.startswith("en"):
                return "en"
            elif lang.startswith("fr"):
                return "fr"
            elif lang.startswith("de"):
                return "de"
            else:
                return "en"
        except:
            return "en"
    
    @staticmethod
    def chunk_text(text, language="en", use_spacy=True):
        """Split text into chunks with improved size control."""
        chunk_size = getattr(config, 'CHUNK_SIZE', 500)
        chunk_overlap = getattr(config, 'CHUNK_OVERLAP', 50)
        
        if use_spacy:
            try:
                pipeline_map = {
                    "en": "en_core_web_sm",
                    "fr": "fr_core_news_sm", 
                    "de": "de_core_news_sm"
                }
                pipeline = pipeline_map.get(language, "en_core_web_sm")
                
                splitter = SpacyTextSplitter(
                    pipeline=pipeline,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )
                chunks = splitter.split_text(text)
                
                # Post-process to ensure chunks don't exceed size limit
                final_chunks = []
                for chunk in chunks:
                    if len(chunk) > chunk_size:
                        # Use recursive splitter as fallback for oversized chunks
                        recursive_splitter = RecursiveCharacterTextSplitter(
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                            separators=["\n\n", "\n", ". ", " ", ""]
                        )
                        sub_chunks = recursive_splitter.split_text(chunk)
                        final_chunks.extend(sub_chunks)
                    else:
                        final_chunks.append(chunk)
                
                return final_chunks
                
            except Exception as e:
                print(f"⚠️ SpaCy chunking failed ({e}), falling back to recursive chunking")
                use_spacy = False
        
        if not use_spacy:
            # Fallback to recursive character splitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
            return splitter.split_text(text)


# -------------------------
# INDICATOR EXTRACTOR
# Extracts cybersecurity and threat intelligence indicators from text
# Supports: domains, URLs, IP addresses, emails, phone numbers, social handles, tracking IDs
# Uses regex patterns and specialized libraries (ipaddress, phonenumbers) for validation
# -------------------------
class IndicatorExtractor:
    """Extracts indicators like domains, IPs, emails from text."""
    
    @staticmethod
    def extract_indicators_by_category(text):
        """Extract various types of indicators from text."""
        indicators = {
            "domains": set(),
            "urls": set(),
            "ips": set(),
            "emails": set(),
            "phones": set(),
            "social_handles": set(),
            "tracking_ids": set()
        }

        # Domains
        file_exts = {"pdf", "html", "htm", "jpg", "jpeg", "png", "gif", "bmp", "tiff", "mp4", "mov", "avi", "webp"}
        domain_pattern = r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,6}\b"
        for match in re.findall(domain_pattern, text):
            if not any(match.lower().endswith(f".{ext}") for ext in file_exts):
                indicators["domains"].add(match.lower())

        # URLs
        url_pattern = r"https?://[^\s/$.?#].[^\s]*"
        indicators["urls"].update(re.findall(url_pattern, text))

        # IPs
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        for match in re.findall(ip_pattern, text):
            try:
                ipaddress.ip_address(match)
                indicators["ips"].add(match)
            except ValueError:
                continue

        # Emails
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        indicators["emails"].update([m.lower() for m in re.findall(email_pattern, text)])

        # Phones
        regions = ["US", "NP", "FR", "DE"]
        for region in regions:
            try:
                for match in phonenumbers.PhoneNumberMatcher(text, region):
                    indicators["phones"].add(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164))
            except:
                continue  # Skip phone parsing errors

        # Social handles
        social_pattern = r"@[\w\-]+"
        indicators["social_handles"].update(re.findall(social_pattern, text))

        # Tracking IDs
        indicators["tracking_ids"].update(re.findall(r"\bUA-\d{4,}-\d+\b", text))
        indicators["tracking_ids"].update(re.findall(r"\bPub-\d{5,}\b", text))

        return {k: sorted(v) for k, v in indicators.items()}


# -------------------------
# FILE MANAGER
# Handles local file system operations for saving processed data
# Creates clean text files and JSON files containing extracted indicators
# Manages directory structure and ensures proper file encoding
# -------------------------
class FileManager:
    """Handles file operations for saving processed data."""
    
    @staticmethod
    def save_clean_and_json(doc_name, full_text, indicators_dict):
        """Save clean text and indicators to files."""
        config.RAW_DIR.mkdir(parents=True, exist_ok=True)
        config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)

        clean_file = config.CLEAN_DIR / f"{doc_name}_clean.txt"
        with open(clean_file, "w", encoding="utf-8") as f:
            f.write(full_text)

        raw_file = config.RAW_DIR / f"{doc_name}_indicators.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(indicators_dict, f, indent=2)

        print(f"💾 Saved clean text -> {clean_file}")
        print(f"💾 Saved indicators -> {raw_file}")


# -------------------------
# POSTGRESQL REPOSITORY
# Handles all PostgreSQL database operations for document and chunk storage
# Manages document metadata, text chunks, embeddings, and indicators
# Uses prepared statements and proper UUID handling for data integrity
# -------------------------
class PostgreSQLRepository:
    """Handles PostgreSQL database operations."""
    
    def __init__(self, cursor, embedding_service):
        self.cur = cursor
        self.embedding_service = embedding_service
    
    def insert_document(self, name, path, language, doc_uuid=None):
        """Insert or retrieve document from PostgreSQL."""
        if doc_uuid is None:
            doc_uuid = str(uuid.uuid4())
        self.cur.execute("SELECT uuid FROM pdf.documents WHERE name = %s", (name,))
        res = self.cur.fetchone()
        if res:
            return res[0]
        self.cur.execute(
            "INSERT INTO pdf.documents (uuid, name, path, language) VALUES (%s, %s, %s, %s)",
            (doc_uuid, name, path, language)
        )
        return doc_uuid

    def insert_chunk(self, document_uuid, text, indicators, page, language, chunk_uuid=None):
        """Insert chunk with embedding into PostgreSQL."""
        if chunk_uuid is None:
            chunk_uuid = str(uuid.uuid4())
        embedding = self.embedding_service.generate_embedding(text)
        self.cur.execute(
            """
            INSERT INTO pdf.chunks (uuid, document_uuid, text, embedding, indicators, page, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (chunk_uuid, document_uuid, text, embedding, indicators, page, language)
        )
        return chunk_uuid


# -------------------------
# NEO4J REPOSITORY
# Handles all Neo4j graph database operations for relationship mapping
# Creates nodes for documents and indicators, establishes relationships
# Manages graph structure for analyzing connections between entities
# Includes connection testing and comprehensive error handling
# -------------------------
class Neo4jRepository:
    """Handles Neo4j graph database operations."""
    
    def __init__(self, driver):
        self.driver = driver
        self._test_connection()
    
    def _test_connection(self):
        """Test Neo4j connection and authentication."""
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
            print("✅ Neo4j connection successful")
        except Exception as e:
            print(f"⚠️ Neo4j connection failed: {e}")
            raise
    
    def insert_document(self, doc_uuid, name, path, lang):
        """Insert document node into Neo4j."""
        try:
            with self.driver.session() as session:
                session.run(
                    "MERGE (d:Document {uuid:$uuid}) "
                    "SET d.name=$name, d.path=$path, d.language=$lang, d.created_at=datetime()",
                    uuid=str(doc_uuid), name=str(name), path=str(path), lang=str(lang)
                )
        except Exception as e:
            print(f"⚠️ Failed to insert document into Neo4j: {e}")
            raise

    def insert_indicators(self, doc_uuid, indicators_by_page):
        """Insert indicators and relationships into Neo4j."""
        try:
            with self.driver.session() as session:
                for page_num, page_indicators in indicators_by_page.items():
                    for category, values in page_indicators.items():
                        for value in values:
                            rel_uuid = str(uuid.uuid4())
                            ind_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{category}:{value}"))
                            session.run(
                                """
                                MERGE (i:Indicator {uuid:$ind_uuid})
                                SET i.value=$val, i.type=$cat, i.created_at=coalesce(i.created_at, datetime())
                                MERGE (d:Document {uuid:$doc_uuid})
                                MERGE (i)-[:MENTIONED_IN {page:$page, category:$cat, relationship_uuid:$rel_uuid}]->(d)
                                """,
                                ind_uuid=ind_uuid, val=value, cat=category,
                                doc_uuid=str(doc_uuid), page=str(page_num), rel_uuid=rel_uuid
                            )
        except Exception as e:
            print(f"⚠️ Failed to insert indicators into Neo4j: {e}")
            raise


# -------------------------
# PDF PROCESSOR (MAIN ORCHESTRATOR)
# The main class that coordinates the entire PDF processing pipeline
# Integrates all services: extraction, processing, database operations, file management
# Handles batch processing of multiple PDFs with comprehensive error handling
# Provides graceful degradation when components fail (e.g., Neo4j unavailable)
# -------------------------
class PDFProcessor:
    """Main orchestrator class for PDF processing."""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.pdf_extractor = PDFExtractor()
        self.text_processor = TextProcessor()
        self.indicator_extractor = IndicatorExtractor()
        self.file_manager = FileManager()
    
    def process_multiple_pdfs(self, cur, neo4j_driver=None):
        """Process multiple PDFs from config.PDFS list."""
        if not hasattr(config, 'PDFS') or not config.PDFS:
            print("⚠️ No PDFs specified in config.PDFS")
            return
        
        processed_count = 0
        for pdf_path in config.PDFS:
            if pdf_path.exists():
                try:
                    self.process_pdf(pdf_path, cur, neo4j_driver)
                    processed_count += 1
                except Exception as e:
                    print(f"❌ Error processing {pdf_path}: {e}")
                    # Continue with next PDF even if one fails
                    continue
            else:
                print(f"❌ File not found: {pdf_path}")
        
        print(f"📊 Processing complete: {processed_count}/{len(config.PDFS)} PDFs processed successfully")
    
    def process_pdf(self, pdf_path: Path, cur, neo4j_driver=None):
        """Main PDF processing pipeline with improved error handling."""
        doc_name = pdf_path.stem
        print(f"🔄 Processing: {doc_name}")
        
        try:
            # Extract and clean text
            raw_pages = self.pdf_extractor.extract_text_from_pdf(pdf_path)
            full_text = " ".join([self.text_processor.clean_text(p["text"]) for p in raw_pages])
            lang = self.text_processor.detect_language(full_text)
            
            # Initialize repositories
            postgres_repo = PostgreSQLRepository(cur, self.embedding_service)
            
            # PostgreSQL operations
            doc_uuid = postgres_repo.insert_document(doc_name, str(pdf_path), lang)
            
            chunks = self.text_processor.chunk_text(full_text, language=lang)
            print(f"📄 Created {len(chunks)} chunks for {doc_name}")
            
            for i, chunk in enumerate(chunks, start=1):
                chunk_indicators = self.indicator_extractor.extract_indicators_by_category(chunk)
                flat_indicators = [v for values in chunk_indicators.values() for v in values]
                postgres_repo.insert_chunk(doc_uuid, chunk, flat_indicators, page=i, language=lang)
            
            # Neo4j operations (with error handling)
            neo4j_success = True
            if neo4j_driver:
                try:
                    neo4j_repo = Neo4jRepository(neo4j_driver)
                    neo4j_repo.insert_document(doc_uuid, doc_name, str(pdf_path), lang)
                    indicators_by_page = {
                        page["page"]: self.indicator_extractor.extract_indicators_by_category(
                            self.text_processor.clean_text(page["text"])
                        )
                        for page in raw_pages
                    }
                    neo4j_repo.insert_indicators(doc_uuid, indicators_by_page)
                except Exception as neo4j_error:
                    print(f"⚠️ Neo4j operations failed for {doc_name}: {neo4j_error}")
                    neo4j_success = False
            
            # Save files
            indicators_dict = self.indicator_extractor.extract_indicators_by_category(full_text)
            indicators_dict["_metadata"] = {
                "document_uuid": doc_uuid,
                "document_name": doc_name,
                "language": lang,
                "total_pages": len(raw_pages),
                "neo4j_success": neo4j_success
            }
            self.file_manager.save_clean_and_json(doc_name, full_text, indicators_dict)
            
            status = "✅" if neo4j_success else "⚠️"
            print(f"{status} Processed '{doc_name}' ({len(chunks)} chunks, {len(raw_pages)} pages)")
            
        except Exception as e:
            print(f"❌ Failed to process {doc_name}: {e}")
            raise
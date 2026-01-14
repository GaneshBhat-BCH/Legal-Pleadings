# COI Management Matching Engine - Technical Architecture

## System Overview

This document provides comprehensive technical diagrams for the COI Management Matching Engine, a FastAPI-based application that uses hybrid search (BM25-style keyword + vector similarity) with Azure OpenAI for document analysis and matching.

### AI Models Used
- **GPT-5** (Azure OpenAI) - Document analysis and Q&A extraction
- **text-embedding-3-large** (Azure OpenAI) - 1536-dimensional embeddings for semantic search

### Search Algorithms
- **BM25-style Ranking** - PostgreSQL's `ts_rank()` function for keyword search (similar to BM25)
- **Cosine Similarity** - Vector distance calculation for semantic search

---

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        CLIENT[Client Application<br/>Frontend/API Consumer]
    end
    
    subgraph "FastAPI Application"
        MAIN[main.py<br/>FastAPI App]
        UPLOAD[Upload Router<br/>/api/upload]
        SEARCH[Search Router<br/>/api/search]
        AI[AI Service<br/>Azure OpenAI]
        LOGGER[Logger Utility<br/>Activity Logging]
        CHUNKING[Chunking Utility<br/>Text Processing]
    end
    
    subgraph "External Services"
        AOAI[Azure OpenAI<br/>GPT-5 + Embeddings]
    end
    
    subgraph "Data Layer"
        PG[(PostgreSQL<br/>with pgvector)]
        DOCS[pdf_documents]
        ANSWERS[pdf_answers]
        CHUNKS[pdf_chunks]
    end
    
    CLIENT -->|HTTP POST| MAIN
    MAIN --> UPLOAD
    MAIN --> SEARCH
    
    UPLOAD --> AI
    SEARCH --> AI
    
    AI -->|Chat Completion| AOAI
    AI -->|Embeddings| AOAI
    
    UPLOAD --> LOGGER
    SEARCH --> LOGGER
    UPLOAD --> CHUNKING
    
    UPLOAD -->|Store| PG
    SEARCH -->|Query| PG
    
    PG --> DOCS
    PG --> ANSWERS
    PG --> CHUNKS
    
    LOGGER -->|Write CSV| ACTLOG[activity_log_*.csv]
    
    style AOAI fill:#0078D4,color:#fff
    style PG fill:#336791,color:#fff
    style MAIN fill:#009688,color:#fff
```

---

## 2. Search Algorithms Explained

### BM25-Style Keyword Search (PostgreSQL ts_rank)

**What is BM25?**
BM25 (Best Matching 25) is a probabilistic ranking function used for keyword-based search. It ranks documents based on term frequency and inverse document frequency.

**Our Implementation:**
We use PostgreSQL's `ts_rank()` function which provides similar functionality to BM25:
- **Term Frequency (TF)**: How often query terms appear in the document
- **Document Length Normalization**: Adjusts for document size
- **Inverse Document Frequency (IDF)**: Rare terms weighted more heavily

**SQL Query:**
```sql
SELECT ts_rank(search_vector, plainto_tsquery('english', query_text)) as rank
FROM pdf_chunks
WHERE search_vector @@ plainto_tsquery('english', query_text)
ORDER BY rank DESC
```

**Advantages:**
- ✅ **FREE** - No API costs
- ✅ **Fast** - Uses GIN index
- ✅ **Accurate** for exact keyword matches

### Vector Similarity Search (Cosine Distance)

**What is Cosine Similarity?**
Measures the angle between two vectors in high-dimensional space (1536 dimensions in our case).

**Our Implementation:**
```sql
SELECT 1 - (chunk_embedding <=> query_embedding) as similarity
FROM pdf_chunks
WHERE 1 - (chunk_embedding <=> query_embedding) > 0.5
ORDER BY similarity DESC
```

**Advantages:**
- ✅ **Semantic understanding** - Finds conceptually similar content
- ✅ **Handles synonyms** - "CEO" matches "Chief Executive Officer"
- ❌ **Costs money** - Requires OpenAI embedding API call

---

## 3. FastAPI Endpoint 1: Document Upload & Ingestion

**Endpoint**: `POST /api/upload`

**Purpose**: Process documents, extract Q&A using GPT-5, generate embeddings, and store in database with dual indexing.

**AI Models Used**:
- **GPT-5** - Forensic document analysis and answer extraction
- **text-embedding-3-large** - Generate 1536-dim vectors for answers and chunks

### 3.1 Upload Endpoint Architecture

```mermaid
graph TB
    subgraph "Client Request"
        CLIENT[POST /api/upload<br/>{file_name, pdf_text, user_text}]
    end
    
    subgraph "Upload Router Processing"
        RECEIVE[1. Receive Request]
        CREATE_DOC[2. Create Document Record]
        COMBINE[3. Combine Context]
        AI_ANALYZE[4. AI Analysis<br/>GPT-5]
        MATCH[5. Match Answers]
        EMBED_ANS[6. Embed Answers<br/>text-embedding-3-large]
        STORE_ANS[7. Store Answers]
        CREATE_CHUNKS[8. Create Chunks]
        EMBED_CHUNKS[9. Embed Chunks<br/>text-embedding-3-large]
        STORE_CHUNKS[10. Store Chunks]
    end
    
    subgraph "Database Tables"
        PDF_DOCS[(pdf_documents)]
        PDF_ANS[(pdf_answers<br/>with embeddings)]
        PDF_CHUNKS[(pdf_chunks<br/>dual indexed)]
    end
    
    subgraph "External AI"
        GPT5[Azure OpenAI<br/>GPT-5]
        EMBED_MODEL[Azure OpenAI<br/>text-embedding-3-large]
    end
    
    CLIENT --> RECEIVE
    RECEIVE --> CREATE_DOC
    CREATE_DOC --> PDF_DOCS
    CREATE_DOC --> COMBINE
    COMBINE --> AI_ANALYZE
    AI_ANALYZE --> GPT5
    GPT5 --> MATCH
    MATCH --> EMBED_ANS
    EMBED_ANS --> EMBED_MODEL
    EMBED_MODEL --> STORE_ANS
    STORE_ANS --> PDF_ANS
    STORE_ANS --> CREATE_CHUNKS
    CREATE_CHUNKS --> EMBED_CHUNKS
    EMBED_CHUNKS --> EMBED_MODEL
    EMBED_MODEL --> STORE_CHUNKS
    STORE_CHUNKS --> PDF_CHUNKS
    
    style GPT5 fill:#0078D4,color:#fff
    style EMBED_MODEL fill:#0078D4,color:#fff
    style PDF_DOCS fill:#336791,color:#fff
    style PDF_ANS fill:#336791,color:#fff
    style PDF_CHUNKS fill:#336791,color:#fff
    style CLIENT fill:#4CAF50,color:#fff
```

### 3.2 Upload Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client (Automation Anywhere)
    participant UploadRouter as Upload Router<br/>/api/upload
    participant Logger
    participant Database as PostgreSQL
    participant AIService as AI Service
    participant AzureOpenAI as Azure OpenAI

    Client->>Client: Extract data from Automation Anywhere
    Client->>UploadRouter: POST /api/upload<br/>{file_name, pdf_text, user_text}
    activate UploadRouter
    
    UploadRouter->>Logger: Log "Upload request received"
    
    Note over UploadRouter: Step 1: Create Document Record
    UploadRouter->>Database: INSERT INTO pdf_documents<br/>(file_name, file_path="text-input")
    Database-->>UploadRouter: Return pdf_id (UUID)
    
    Note over UploadRouter: Step 2: Prepare Context
    UploadRouter->>UploadRouter: Combine input:<br/>full_context = "User Input: " + user_text<br/>+ "Document Content: " + pdf_text
    
    Note over UploadRouter: Step 3: AI Analysis (Question Extraction)
    UploadRouter->>AIService: analyze_document_and_answer(full_context, QUESTIONS_DATA)
    activate AIService
    AIService->>AzureOpenAI: Chat Completion (model: gpt-5)<br/>System: "Forensic auditor AI"<br/>Prompt: Extract answers based on QUESTIONS_DATA
    AzureOpenAI-->>AIService: JSON {answers: [...], usage: {...}}
    AIService-->>UploadRouter: Return answers & usage
    deactivate AIService
    
    Note over UploadRouter: Step 4: Process Answers
    UploadRouter->>UploadRouter: Normalize answers (assign 'N/A' if missing)<br/>Map to Question IDs
    
    Note over UploadRouter: Step 5: Answer Embeddings
    UploadRouter->>AIService: get_embeddings(texts_to_embed)
    activate AIService
    AIService->>AzureOpenAI: Embeddings Batch Request<br/>(model: text-embedding-3-large, dim: 1536)
    AzureOpenAI-->>AIService: Return list of vectors
    AIService-->>UploadRouter: Return all_embeddings
    deactivate AIService
    
    Note over UploadRouter: Step 6: Store Answers
    UploadRouter->>Database: INSERT INTO pdf_answers<br/>(pdf_id, question_id, answer_text, answer_embedding)
    
    Note over UploadRouter: Step 7: Variable Chunking Strategy (RAG)
    UploadRouter->>UploadRouter: semantic variable checking
    
    Note over UploadRouter: Step 8: Chunk Embeddings
    UploadRouter->>AIService: get_embeddings(chunks_to_index)
    activate AIService
    AIService->>AzureOpenAI: Embeddings Batch Request<br/>(model: text-embedding-3-large)
    AzureOpenAI-->>AIService: Return chunk_vectors
    AIService-->>UploadRouter: Return vectors
    deactivate AIService
    
    Note over UploadRouter: Step 9: Store Chunks (Dual Indexing)
    UploadRouter->>Database: INSERT INTO pdf_chunks (chunk_embedding, search_vector)<br/>search_vector = to_tsvector('english', chunk_text)
    Note over Database: Indexes Updated:<br/>1. IVFFlat (Vector Ops)<br/>2. GIN (Full-Text Search)
    
    UploadRouter->>Logger: Log "Processing Complete"
    UploadRouter-->>Client: Return JSON Response<br/>{status, pdf_id, answers, chunks_created}
    deactivate UploadRouter
```

### Upload Flow - Detailed Steps

| Step | Component | Action | Database Impact |
|------|-----------|--------|-----------------|
| 1 | Upload Router | Receive document data | - |
| 2 | Database | Create document record | INSERT `pdf_documents` |
| 3 | AI Service | Analyze document with GPT-5 | - |
| 4 | Upload Router | Process AI responses | - |
| 5 | AI Service | Generate answer embeddings | - |
| 6 | Database | Store answers with vectors | INSERT `pdf_answers` |
| 7 | Upload Router | Create searchable chunks | - |
| 8 | AI Service | Generate chunk embeddings | - |
| 9 | Database | Store chunks with dual index | INSERT `pdf_chunks` |

---

## 3. FastAPI Endpoint 2: Hybrid Search

**Endpoint**: `POST /api/search`

**Purpose**: Find matching documents using cost-optimized hybrid search (BM25-style keyword-first, vector fallback).

**Search Algorithms**:
- **Primary**: PostgreSQL `ts_rank()` - BM25-style keyword ranking (FREE)
- **Fallback**: Cosine similarity on embeddings (requires OpenAI API call)

**AI Models Used** (conditional):
- **text-embedding-3-large** - Generate query embedding (only if keyword search insufficient)

### 3.1 Search Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client (Automation Anywhere)
    participant SearchRouter as Search Router<br/>/api/search
    participant Logger
    participant Database as PostgreSQL
    participant AIService as AI Service
    participant AzureOpenAI as Azure OpenAI

    Client->>SearchRouter: POST /api/search<br/>{questions_answers: [...]}
    activate SearchRouter
    
    Note over SearchRouter: Step 1: Query Construction
    SearchRouter->>SearchRouter: Concatenate Q&A pairs -> query_text
    
    Note over SearchRouter: Step 2: BM25-Style Keyword Search (Primary)
    SearchRouter->>Database: SELECT ... ts_rank(search_vector, plainto_tsquery('english', :query))<br/>FROM pdf_chunks ... ORDER BY rank DESC LIMIT 10
    Database-->>SearchRouter: Return Keyword Candidates
    
    Note over SearchRouter: Step 3: Forensic Verification(AI Auditor ) (Stage 1)
    loop For each Candidate
        SearchRouter->>Database: Fetch stored answers (pdf_answers)
        SearchRouter->>SearchRouter: Verification Logic:<br/>1. Match Request Q vs Stored Q (ID/Text)<br/>2. If Match: Extract User Ref Tokens & Stored Answer Tokens<br/>3. Strict Check: If no token overlap, mark Mismatch (Lenient)
        SearchRouter->>SearchRouter: Count Valid Matches (valid_match_count)
    end
    
    SearchRouter->>SearchRouter: Filter verified_candidates (valid_match_count > 0)
    
    alt Verified Count < 3 (Insufficient Results)
        Note over SearchRouter: Step 4: Hybrid Fallback (Vector Search)
        SearchRouter->>Logger: Log "Augmenting with Vector Search"
        
        SearchRouter->>AIService: get_embeddings(query_text)
        activate AIService
        AIService->>AzureOpenAI: Embeddings Request (text-embedding-3-large)
        AzureOpenAI-->>AIService: Return query_vector
        AIService-->>SearchRouter: Return vector
        deactivate AIService
        
        SearchRouter->>Database: SELECT ... (1 - (chunk_embedding <=> :vector)) > 0.5<br/>ORDER BY similarity DESC LIMIT 10
        Database-->>SearchRouter: Return Vector Candidates
        
        SearchRouter->>SearchRouter: Filter Duplicate PDFs (already found by keyword)
        
        Note over SearchRouter: Step 5: Forensic Verification(AI Auditor ) (Stage 2)
        loop For each New Candidate
            SearchRouter->>Database: Fetch stored answers
            SearchRouter->>SearchRouter: Run Verification Logic
        end
        
        SearchRouter->>SearchRouter: Combine Keyword + Vector Candidates
    else Verified Count >= 3
        Note over SearchRouter: Keyword Search Sufficient (Skip Vector)
        SearchRouter->>Logger: Log "Skipping Vectorization (Cost Savings)"
    end
    
    Note over SearchRouter: Step 6: Final Ranking & Response
    SearchRouter->>SearchRouter: Sort by (Valid Match Count DESC, Match Score DESC)<br/>Select Top 3
    SearchRouter-->>Client: Return {search_method, results: [Top 3]}
    deactivate SearchRouter
```

### Search Strategy Decision Tree

```mermaid
flowchart TD
    START([Receive Search Request])
    PREP[Prepare Query Text<br/>Combine Q&A pairs]
    KEYWORD[Execute BM25-Style Search<br/>PostgreSQL ts_rank]
    VERIFY1[Verify Keyword Results<br/>Match Q&A pairs]
    CHECK{Verified<br/>PDFs >= 3?}
    DONE1[Return Results<br/>Method: SQL Keyword Free]
    EMBED[Generate Query Embedding<br/>Azure OpenAI]
    VECTOR[Execute Vector Search<br/>Cosine Similarity]
    FILTER[Filter Out Duplicate PDFs]
    VERIFY2[Verify Vector Results<br/>Match Q&A pairs]
    COMBINE[Combine Keyword + Vector<br/>Candidates]
    DONE2[Return Results<br/>Method: Hybrid]
    
    START --> PREP
    PREP --> KEYWORD
    KEYWORD --> VERIFY1
    VERIFY1 --> CHECK
    CHECK -->|Yes| DONE1
    CHECK -->|No| EMBED
    EMBED --> VECTOR
    VECTOR --> FILTER
    FILTER --> VERIFY2
    VERIFY2 --> COMBINE
    COMBINE --> DONE2
    
    style START fill:#4CAF50,color:#fff
    style DONE1 fill:#2196F3,color:#fff
    style DONE2 fill:#FF9800,color:#fff
    style EMBED fill:#F44336,color:#fff,stroke:#000,stroke-width:3px
    style CHECK fill:#9C27B0,color:#fff
```

---

## 4. Database Schema

```mermaid
erDiagram
    pdf_documents ||--o{ pdf_answers : "has many"
    pdf_documents ||--o{ pdf_chunks : "has many"
    
    pdf_documents {
        UUID pdf_id PK "Primary Key"
        TEXT file_name "Document name"
        TEXT file_path "Storage path"
        TIMESTAMP uploaded_at "Upload timestamp"
    }
    
    pdf_answers {
        BIGSERIAL id PK "Primary Key"
        UUID pdf_id FK "Foreign Key"
        INT question_id "Question identifier"
        TEXT question_text "Question content"
        TEXT answer_text "Extracted answer"
        VECTOR_1536 answer_embedding "Answer vector"
        TIMESTAMP created_at "Creation timestamp"
    }
    
    pdf_chunks {
        BIGSERIAL id PK "Primary Key"
        UUID pdf_id FK "Foreign Key"
        TEXT chunk_text "Searchable text chunk"
        VECTOR_1536 chunk_embedding "Chunk vector"
        TSVECTOR search_vector "Full-text search vector"
        TIMESTAMP created_at "Creation timestamp"
    }
    
    user_queries {
        UUID query_id PK "Primary Key"
        TEXT user_id "User identifier"
        INT question_id "Question identifier"
        TEXT question_text "Question content"
        TEXT user_answer "User's answer"
        VECTOR_1536 user_embedding "User answer vector"
        TIMESTAMP created_at "Query timestamp"
    }
```

### Database Indexes

```mermaid
graph LR
    subgraph "pdf_chunks Table"
        CHUNKS[chunk_text<br/>chunk_embedding<br/>search_vector]
    end
    
    subgraph "Indexes"
        IVFFLAT[IVFFlat Index<br/>vector_cosine_ops<br/>lists=100]
        GIN[GIN Index<br/>Full-Text Search]
    end
    
    subgraph "Query Types"
        VECTOR_Q[Vector Similarity<br/>Cosine Distance]
        TEXT_Q[Keyword Search<br/>ts_rank]
    end
    
    CHUNKS -->|chunk_embedding| IVFFLAT
    CHUNKS -->|search_vector| GIN
    
    IVFFLAT -.->|Optimizes| VECTOR_Q
    GIN -.->|Optimizes| TEXT_Q
    
    style IVFFLAT fill:#FF6B6B,color:#fff
    style GIN fill:#4ECDC4,color:#fff
    style VECTOR_Q fill:#95E1D3,color:#000
    style TEXT_Q fill:#F38181,color:#fff
```

---

## 5. Technology Stack

```mermaid
graph TB
    subgraph "Application Layer"
        FASTAPI[FastAPI<br/>Web Framework]
        UVICORN[Uvicorn<br/>ASGI Server]
        PYDANTIC[Pydantic<br/>Data Validation]
    end
    
    subgraph "AI & ML"
        OPENAI[Azure OpenAI<br/>GPT-5]
        EMBED[text-embedding-3-large<br/>1536 dimensions]
        TIKTOKEN[tiktoken<br/>Token Counting]
    end
    
    subgraph "Database"
        POSTGRES[PostgreSQL<br/>Relational DB]
        PGVECTOR[pgvector Extension<br/>Vector Storage]
        ASYNCPG[asyncpg<br/>Async Driver]
        DATABASES[databases<br/>Async ORM]
    end
    
    subgraph "Utilities"
        DOTENV[python-dotenv<br/>Config Management]
        HTTPX[httpx<br/>HTTP Client]
        MULTIPART[python-multipart<br/>File Upload]
    end
    
    FASTAPI --> UVICORN
    FASTAPI --> PYDANTIC
    FASTAPI --> OPENAI
    FASTAPI --> EMBED
    FASTAPI --> TIKTOKEN
    
    FASTAPI --> ASYNCPG
    ASYNCPG --> DATABASES
    DATABASES --> POSTGRES
    POSTGRES --> PGVECTOR
    
    FASTAPI --> DOTENV
    FASTAPI --> HTTPX
    FASTAPI --> MULTIPART
    
    style FASTAPI fill:#009688,color:#fff
    style OPENAI fill:#0078D4,color:#fff
    style POSTGRES fill:#336791,color:#fff
```

---

## 6. API Endpoints

### Upload Endpoint

**POST** `/api/upload`

**Request Body:**
```json
{
  "file_name": "document.pdf",
  "pdf_text": "Full document content...",
  "user_text": "Additional context or instructions"
}
```

**Response:**
```json
{
  "status": "success",
  "pdf_id": "uuid-here",
  "extracted_text_preview": "First 200 chars...",
  "answers": [
    {
      "question_id": 1,
      "question_text": "What is...",
      "answer_text": "Extracted answer"
    }
  ],
  "chunks_created": 15,
  "token_usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 300,
    "total_tokens": 1800
  }
}
```

### Search Endpoint

**POST** `/api/search`

**Request Body:**
```json
{
  "questions_answers": [
    {
      "question_id": 1,
      "question_text": "What is...",
      "answer_text": "User's answer"
    }
  ]
}
```

**Response:**
```json
{
  "search_method_used": "SQL Keyword (Free)",
  "results": [
    {
      "pdf_name": "document.pdf",
      "match_score": "85.5%",
      "search_method": "SQL Keyword (Free)",
      "relevance_details": {
        "vector": 0.855,
        "keyword_rank": 0.234
      },
      "matched_qa": [
        {
          "question": "What is...",
          "pdf_answer": "Stored answer",
          "user_answer_ref": "User's answer"
        }
      ],
      "unmatched_qa": []
    }
  ]
}
```

---

## 7. Cost Optimization Strategy

```mermaid
flowchart LR
    subgraph "Upload Phase - Always Uses AI"
        U1[Document Analysis<br/>GPT-5 Chat]
        U2[Answer Embeddings<br/>Batch API]
        U3[Chunk Embeddings<br/>Batch API]
    end
    
    subgraph "Search Phase - Conditional AI"
        S1[Keyword Search<br/>FREE - PostgreSQL]
        S2{Sufficient<br/>Results?}
        S3[Return Results<br/>NO AI COST]
        S4[Query Embedding<br/>PAID - OpenAI]
        S5[Vector Search<br/>PostgreSQL]
        S6[Return Results<br/>WITH AI COST]
    end
    
    U1 --> U2 --> U3
    
    S1 --> S2
    S2 -->|Yes >= 3| S3
    S2 -->|No < 3| S4
    S4 --> S5 --> S6
    
    style U1 fill:#F44336,color:#fff
    style U2 fill:#F44336,color:#fff
    style U3 fill:#F44336,color:#fff
    style S1 fill:#4CAF50,color:#fff
    style S3 fill:#4CAF50,color:#fff
    style S4 fill:#F44336,color:#fff
    
    COST1[💰 Upload: ~$0.01-0.05 per document]
    COST2[💰 Search: $0 if keyword works<br/>~$0.001 if vector needed]
```

### Cost Breakdown

| Operation | Model | Cost Factor | Optimization |
|-----------|-------|-------------|--------------|
| Document Analysis | GPT-5 | High | Batch questions in single call |
| Answer Embeddings | text-embedding-3-large | Medium | Batch API (multiple texts at once) |
| Chunk Embeddings | text-embedding-3-large | Medium | Batch API |
| BM25-Style Keyword Search | PostgreSQL ts_rank | **FREE** | Primary search method |
| Vector Search | PostgreSQL + OpenAI | Low | Only when keyword insufficient |

---

## 8. Data Flow Summary

```mermaid
sankey-beta

Upload Flow,Document Record,1
Upload Flow,AI Analysis,1
Upload Flow,Answer Storage,1
Upload Flow,Chunk Storage,1

AI Analysis,GPT-5 Chat,1
Answer Storage,Embeddings API,1
Chunk Storage,Embeddings API,1

Search Flow,Keyword Search,10
Search Flow,Vector Search,3

Keyword Search,Verified Results,7
Keyword Search,Insufficient Results,3

Insufficient Results,Vector Search,3
Vector Search,Verified Results,3

Verified Results,Top 3 Results,10
```

---

## Key Design Decisions

1. **Hybrid Search Strategy**: Keyword-first approach minimizes AI costs while maintaining accuracy
2. **Batch Embeddings**: All embeddings generated in batch calls for efficiency
3. **Dual Indexing**: Both vector (ivfflat) and text (GIN) indexes on chunks table
4. **Verification Layer**: All search results verified by matching Q&A pairs, not just similarity scores
5. **Structured Chunks**: Only Q&A pairs and context indexed, not raw document text
6. **Token-Based Matching**: Lenient matching algorithm for Q&A verification
7. **Activity Logging**: All operations logged to CSV for audit trail

---

## Performance Characteristics

- **Upload Latency**: 2-5 seconds (depends on document size and question count)
- **Search Latency**: 
  - Keyword-only: 100-300ms
  - Hybrid: 500-1000ms
- **Database**: PostgreSQL with pgvector extension
- **Scalability**: Horizontal scaling via multiple Uvicorn workers
- **Concurrency**: Async/await throughout for non-blocking I/O

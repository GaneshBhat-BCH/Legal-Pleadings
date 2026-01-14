CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS coi_mgmt;

CREATE TABLE IF NOT EXISTS coi_mgmt.pdf_documents (
    pdf_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    input_body TEXT,
    result_body TEXT,
    uploaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coi_mgmt.pdf_answers (
    id BIGSERIAL PRIMARY KEY,
    pdf_id UUID REFERENCES coi_mgmt.pdf_documents(pdf_id) ON DELETE CASCADE,
    question_id INT NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    answer_embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coi_mgmt.user_queries (
    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    question_id INT NOT NULL,
    question_text TEXT NOT NULL,
    user_answer TEXT,
    user_embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coi_mgmt.pdf_chunks (
    id BIGSERIAL PRIMARY KEY,
    pdf_id UUID REFERENCES coi_mgmt.pdf_documents(pdf_id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_embedding VECTOR(1536),
    search_vector TSVECTOR,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pdf_chunks_embedding ON coi_mgmt.pdf_chunks USING ivfflat (chunk_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_pdf_chunks_search ON coi_mgmt.pdf_chunks USING gin(search_vector);

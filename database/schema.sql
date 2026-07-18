CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT CHECK(file_type IN ('docx', 'pdf')),
    source_group_id TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_text TEXT,
    status TEXT DEFAULT 'uploaded' 
);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    field_name TEXT NOT NULL,
    field_value TEXT,
    confidence REAL,
    method TEXT,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parties (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    name TEXT NOT NULL,
    role TEXT,
    inn TEXT,
    ogrn TEXT
);

CREATE TABLE IF NOT EXISTS ground_truth (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    field_name TEXT NOT NULL,
    true_value TEXT NOT NULL
);

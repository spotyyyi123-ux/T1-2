import json
import sqlite3
import uuid

conn = sqlite3.connect('database/contracts.db')
cursor = conn.cursor()

with open('dataset/annotations/labels.json', 'r', encoding='utf-8') as f:
    labels = json.load(f)

for label in labels:
    doc_id = str(uuid.uuid4())
    
    cursor.execute(
        "INSERT INTO documents (id, filename, file_path, file_type) VALUES (?, ?, ?, ?)",
        (doc_id, label['file'], f"dataset/docx/{label['file']}", 'docx')
    )
    
    fields = [
        ('number', label['number']),
        ('date', label['date']),
        ('amount', str(label['amount'])),
        ('amount_text', label.get('amount_text', '')),
        ('kind', label.get('kind', '')),
    ]
    
    for field_name, field_value in fields:
        cursor.execute(
            "INSERT INTO ground_truth (id, document_id, field_name, true_value) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), doc_id, field_name, field_value)
        )
    
    for party in label['parties']:
        cursor.execute(
            "INSERT INTO parties (id, document_id, name, role, inn, ogrn) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), doc_id, 
             party['name'], party.get('role', ''),
             party.get('inn', ''), party.get('ogrn', ''))
        )

conn.commit()
conn.close()
print(f'Загружено {len(labels)} договоров в базу данных')

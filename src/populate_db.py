import json
import sqlite3
import uuid
from pathlib import Path

conn = sqlite3.connect('database/contracts.db')
cursor = conn.cursor()

# Загружаем разметку
with open('dataset/annotations/labels.json', 'r', encoding='utf-8') as f:
    labels = json.load(f)

for label in labels:
    doc_id = str(uuid.uuid4())
    filename = label['file']
    
    # Вставляем DOCX
    cursor.execute(
        "INSERT INTO documents (id, filename, file_path, file_type) VALUES (?, ?, ?, ?)",
        (doc_id, filename, f"dataset/docx/{filename}", 'docx')
    )
    
    # Если есть PDF-версия — добавляем и её
    pdf_filename = filename.replace('.docx', '.pdf')
    pdf_path = Path(f"dataset/pdf/{pdf_filename}")
    if pdf_path.exists():
        pdf_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO documents (id, filename, file_path, file_type) VALUES (?, ?, ?, ?)",
            (pdf_id, pdf_filename, f"dataset/pdf/{pdf_filename}", 'pdf')
        )
    
    # Вставляем эталонные поля (для DOCX)
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
    
    # Вставляем стороны
    for party in label['parties']:
        cursor.execute(
            "INSERT INTO parties (id, document_id, name, role, inn, ogrn) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), doc_id, 
             party['name'], party.get('role', ''),
             party.get('inn', ''), party.get('ogrn', ''))
        )

conn.commit()
conn.close()

# Подсчитаем статистику
import sqlite3
conn = sqlite3.connect('database/contracts.db')
cursor = conn.cursor()
cursor.execute("SELECT file_type, COUNT(*) FROM documents GROUP BY file_type")
stats = cursor.fetchall()
print("Загружено в базу:")
for file_type, count in stats:
    print(f"  {file_type}: {count} шт.")
conn.close()
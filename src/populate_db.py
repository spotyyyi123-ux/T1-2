import json
import sqlite3
import uuid
from pathlib import Path

conn = sqlite3.connect('database/contracts.db')
cursor = conn.cursor()

with open('dataset/annotations/labels.json', 'r', encoding='utf-8') as f:
    labels = json.load(f)

for label in labels:
    filename = label['file']
    source_group_id = filename.replace('.docx', '')  # общий ключ для docx+pdf
    
    # Вставляем DOCX
    docx_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO documents (id, filename, file_path, file_type, source_group_id) VALUES (?, ?, ?, ?, ?)",
        (docx_id, filename, f"dataset/docx/{filename}", 'docx', source_group_id)
    )
    
    # Вставляем PDF (если есть)
    pdf_filename = filename.replace('.docx', '.pdf')
    pdf_path = Path(f"dataset/pdf/{pdf_filename}")
    pdf_id = None
    if pdf_path.exists():
        pdf_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO documents (id, filename, file_path, file_type, source_group_id) VALUES (?, ?, ?, ?, ?)",
            (pdf_id, pdf_filename, f"dataset/pdf/{pdf_filename}", 'pdf', source_group_id)
        )
    
    # Вставляем эталонные поля — привязываем к source_group_id (один раз на договор)
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
            (str(uuid.uuid4()), source_group_id, field_name, field_value)
        )
    
    # Вставляем стороны — тоже привязываем к source_group_id
    for party in label['parties']:
        cursor.execute(
            "INSERT INTO parties (id, document_id, name, role, inn, ogrn) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), source_group_id,
             party['name'], party.get('role', ''),
             party.get('inn', ''), party.get('ogrn', ''))
        )

conn.commit()
conn.close()

# Статистика
conn = sqlite3.connect('database/contracts.db')
cursor = conn.cursor()
cursor.execute("SELECT file_type, COUNT(*) FROM documents GROUP BY file_type")
for file_type, count in cursor.fetchall():
    print(f"  {file_type}: {count} шт.")
cursor.execute("SELECT COUNT(*) FROM ground_truth")
print(f"  Эталонных полей: {cursor.fetchone()[0]} шт.")
cursor.execute("SELECT COUNT(*) FROM parties")
print(f"  Сторон: {cursor.fetchone()[0]} шт.")
conn.close()
# ContractAI — Sprint 1

Автоматизация извлечения полей (номер, дата, сумма, стороны) из договоров.

## Порядок запуска

### 1. Генерация датасета

python src/generate_contracts.py --count 30 --out ./dataset

Создаёт 30 DOCX-договоров и labels.json с эталонной разметкой.

### 2. Конвертация в PDF (Windows + Word)

powershell -File src/convert_to_pdf.ps1

Создаёт PDF-версии первых 10 договоров.

### 3. Создание базы данных и загрузка разметки

sqlite3 database/contracts.db < database/schema.sql
python src/populate_db.py

Создаёт SQLite-базу и заполняет её данными из labels.json.

## Структура проекта

| Папка | Содержимое |
|-------|------------|
| dataset/docx/ | 30 синтетических договоров |
| dataset/pdf/ | 10 PDF-версий |
| dataset/annotations/ | labels.json + manual_labels.csv |
| database/ | schema.sql + contracts.db |
| docs/ | architecture.md + api_contract.md |
| src/ | generate_contracts.py, populate_db.py, convert_to_pdf.ps1 |

## Зависимости

pip install -r requirements.txt
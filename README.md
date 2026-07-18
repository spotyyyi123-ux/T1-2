# ContractAI — Sprint 1

Автоматизация извлечения полей (номер, дата, сумма, стороны) из договоров.

## Порядок запуска

### 1. Генерация датасета
```bash
python src/generate_contracts.py --count 30 --out ./dataset
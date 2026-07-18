# API Contract — ContractAI

Соглашение о формате JSON между бэкендом и фронтендом.

---

## 1. Загрузка договора

### POST /upload

Что делает: Пользователь загружает DOCX или PDF файл.

Успешный ответ (201 Created):

{
  "document_id": "abc-123-def",
  "filename": "dogovor.docx",
  "status": "uploaded"
}

Ошибка (400 Bad Request):

{
  "error": "Неподдерживаемый формат файла"
}

---

## 2. Список договоров (реестр)

### GET /documents

Что делает: Возвращает таблицу всех договоров.

Успешный ответ (200 OK):

{
  "total": 30,
  "documents": [
    {
      "document_id": "abc-123-def",
      "filename": "dogovor_1.docx",
      "number": "№ 145-Д/2024",
      "date": "2024-03-12",
      "amount": 1250000,
      "customer": "ООО «Ромашка»",
      "executor": "АО «Вертикаль»"
    }
  ]
}

---

## 3. Детали одного договора

### GET /documents/{document_id}

Что делает: Возвращает все извлеченные поля.

Успешный ответ (200 OK):

{
  "document_id": "abc-123-def",
  "filename": "dogovor_1.docx",
  "raw_text": "ДОГОВОР № 145-Д/2024 от 12 марта 2024...",
  "fields": {
    "number": "№ 145-Д/2024",
    "date": "2024-03-12",
    "amount": 1250000,
    "amount_text": "один миллион двести пятьдесят тысяч рублей 00 копеек",
    "parties": [
      {
        "name": "ООО «Ромашка»",
        "role": "Заказчик",
        "inn": "7701234567"
      },
      {
        "name": "АО «Вертикаль»",
        "role": "Исполнитель",
        "inn": "5001002003"
      }
    ]
  }
}

---

## Правила оформления полей

| Поле | Тип | Правило |
|------|-----|---------|
| document_id | string (UUID) | Уникальный ID |
| filename | string | Имя файла |
| status | string | uploaded / processing / completed / error |
| date | string | Всегда YYYY-MM-DD |
| amount | integer | Всегда число, не строка |
| parties | array | Всегда массив объектов |

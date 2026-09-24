"""Normalize extraction data and produce a separate, human-readable presentation.

No database writes: normalizing a legacy response is safe to do at read time.
Money uses Decimal so formatting never passes through binary float arithmetic.
"""

import re
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation


class AIServiceError(RuntimeError):
    """An expected failure from the external LLM service."""


NOT_FOUND = "Не найдено"
EXTRACTION_FIELDS = (
    "contract_number", "contract_date", "subject", "customer", "contractor",
    "amount", "currency", "vat_rate", "payment_terms", "performance_deadline",
    "validity_period", "penalty_terms", "termination_terms",
)
ROLE_LABELS = {
    "customer": "Заказчик", "client": "Заказчик", "buyer": "Покупатель",
    "contractor": "Исполнитель", "contracter": "Исполнитель",
    "executor": "Исполнитель", "supplier": "Поставщик", "seller": "Продавец",
}
CURRENCY_PATTERNS = {
    "RUB": r"₽|\brub\b|\brur\b|\bруб(?:\.|лей|ля|ль)?(?!\w)",
    "USD": r"\$|\busd\b|\bдоллар(?:ов|а|ы)?(?:\s+сша)?\b",
    "EUR": r"€|\beur\b|\bевро\b",
    "GBP": r"£|\bgbp\b|\bфунт(?:ов|а|ы)?(?:\s+стерлингов)?\b",
    "CNY": r"\bcny\b|\bюан(?:ь|я|ей)\b",
    "KZT": r"₸|\bkzt\b|\bтенге\b",
    "BYN": r"\bbyn\b",
    "CHF": r"\bchf\b",
}
MISSING_VALUES = {"", "не найдено", "не указано", "не указан", "нет данных", "null", "none", "n/a", "-", "—"}
MONTHS = {
    name: number for number, name in enumerate((
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ), 1)
}


def to_display_string(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return NOT_FOUND
    if isinstance(value, (float, Decimal)):
        number = Decimal(str(value))
        if not number.is_finite():
            return NOT_FOUND
        value = format(number, "f")
    if isinstance(value, (str, int, float, Decimal)):
        text = re.sub(r"\s+", " ", str(value)).strip()
        return NOT_FOUND if text.casefold() in MISSING_VALUES else text
    if isinstance(value, list):
        return "; ".join(text for item in value if (text := to_display_string(item)) != NOT_FOUND) or NOT_FOUND
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = to_display_string(item)
            if text != NOT_FOUND:
                label = ROLE_LABELS.get(str(key).strip().lower(), str(key).strip())
                parts.append(f"{label}: {text}")
        return "; ".join(parts) or NOT_FOUND
    return NOT_FOUND


def split_parties(value: object) -> tuple[str, str]:
    """Support old role dictionaries and their already flattened string form."""
    if isinstance(value, str):
        pairs = re.findall(
            r"(?:^|;\s*)(customer|client|buyer|заказчик|покупатель|contractor|contracter|executor|supplier|seller|исполнитель|подрядчик|поставщик|продавец)\s*:\s*([^;]+)",
            value, flags=re.IGNORECASE,
        )
        if pairs:
            value = dict(pairs)
    if not isinstance(value, dict):
        return to_display_string(value), NOT_FOUND
    customer_roles = {"customer", "client", "buyer", "заказчик", "покупатель"}
    contractor_roles = {"contractor", "contracter", "executor", "supplier", "seller", "исполнитель", "подрядчик", "поставщик", "продавец"}
    customer, contractor = [], []
    for role, party in value.items():
        role = str(role).strip().lower()
        text = to_display_string(party)
        if text != NOT_FOUND:
            if role in customer_roles:
                customer.append(text)
            elif role in contractor_roles:
                contractor.append(text)
    return "; ".join(customer) or NOT_FOUND, "; ".join(contractor) or NOT_FOUND


def normalize_date(value: str) -> str:
    """Format complete, valid dates; preserve relative terms and date ranges."""
    cleaned = re.sub(r"\s*г(?:\.|ода)?$", "", value, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'[«»"]', "", cleaned)
    words = re.fullmatch(r"(\d{1,2})\s+(\w+)\s+(\d{4})", cleaned)
    if words and words[2].lower() in MONTHS:
        cleaned = f"{words[1]}.{MONTHS[words[2].lower()]}.{words[3]}"
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            pass
    return value


def currency_in(text: str) -> str:
    matches = [code for code, pattern in CURRENCY_PATTERNS.items() if re.search(pattern, text, re.IGNORECASE)]
    return matches[0] if len(matches) == 1 else NOT_FOUND


def normalize_currency(value: str, amount: str) -> str:
    if value != NOT_FOUND:
        known = currency_in(value)
        if known != NOT_FOUND:
            return known
        return value.upper() if re.fullmatch(r"[A-Za-z]{3}", value) else value
    return currency_in(amount)


def normalize_amount(value: object) -> Decimal | None:
    """Accept exact cents; never round or guess ambiguous separator notation."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        # JSON numbers already have an unambiguous decimal separator. Do not
        # pass 1.234 through the legacy thousands-separator parser.
        amount = Decimal(str(value))
        if not amount.is_finite():
            return None
        sign, digits, exponent = amount.as_tuple()
        excess = max(0, -exponent - 2)
        if excess and any(digits[-excess:]):
            return None
        # Remove insignificant extra fractional zeros, without Decimal context
        # rounding (large monetary values must retain every digit).
        if excess:
            amount = Decimal((sign, digits[:-excess] or (0,), -2))
        return amount
    if not isinstance(value, str):
        return None
    value = to_display_string(value)
    if value == NOT_FOUND:
        return None
    cleaned = value
    # Two explicit currencies may indicate two prices; leave such text intact.
    if sum(bool(re.search(pattern, cleaned, re.IGNORECASE)) for pattern in CURRENCY_PATTERNS.values()) > 1:
        return None
    for pattern in CURRENCY_PATTERNS.values():
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    kopecks = re.fullmatch(r"\s*([\d\s]+)\s+(\d{1,2})\s*коп(?:\.|еек|ейки|ейка)?\s*", cleaned, re.IGNORECASE)
    if kopecks:
        cleaned = f"{kopecks[1].strip()},{int(kopecks[2]):02d}"
    cleaned = cleaned.strip()
    # Spaces separate groups of three digits, not separate amounts.
    if re.search(r"\d\s+\d", cleaned) and not re.fullmatch(r"[+-]?\d{1,3}(?:\s+\d{3})+(?:[.,]\d{1,2})?", cleaned):
        return None
    cleaned = re.sub(r"\s+", "", cleaned)
    # A lone dot/comma with three trailing digits may mean thousands OR
    # fractions. Preserve it for review instead of silently multiplying by 1000.
    if re.fullmatch(r"[+-]?\d{1,3}[.,]\d{3}", cleaned):
        return None
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d{1,2})?", cleaned):
        decimal_text = cleaned.replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", cleaned):
        decimal_text = cleaned.replace(",", "")
    elif re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", cleaned):
        decimal_text = cleaned.replace(".", "").replace(",", ".")
    else:
        return None
    try:
        amount = Decimal(decimal_text)
        if not amount.is_finite():
            return None
        return amount
    except InvalidOperation:
        return None


def normalize_ai_attributes(result: object) -> dict:
    if not isinstance(result, dict):
        raise AIServiceError("LLM-провайдер вернул JSON с неверной схемой")
    source = dict(result)
    source.setdefault("contract_number", source.get("number"))
    source.setdefault("contract_date", source.get("date"))
    if "parties" in source:
        customer, contractor = split_parties(source["parties"])
        source.setdefault("customer", customer)
        source.setdefault("contractor", contractor)
    # Keep rejected values for manual review, including after repeated normalization.
    previous_raw = source.get("unparsed_values", {})
    raw = {field: to_display_string(value) for field, value in previous_raw.items()
           if field in EXTRACTION_FIELDS and to_display_string(value) != NOT_FOUND} if isinstance(previous_raw, dict) else {}
    texts = {field: to_display_string(source.get(field)) for field in EXTRACTION_FIELDS}
    normalized = {field: None if value == NOT_FOUND else value for field, value in texts.items()}
    currency = normalize_currency(texts["currency"], texts["amount"])
    normalized["currency"] = currency if re.fullmatch(r"[A-Z]{3}", currency) else None
    normalized["amount"] = normalize_amount(source.get("amount"))
    for field in ("contract_date", "performance_deadline", "validity_period"):
        if normalized[field] is not None:
            normalized[field] = normalize_date(normalized[field])
    if normalized["contract_date"] is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized["contract_date"]):
        normalized["contract_date"] = None
    # An ISO-shaped but impossible date must also fail validation.
    if normalized["contract_date"] is not None:
        try:
            datetime.strptime(normalized["contract_date"], "%Y-%m-%d")
        except ValueError:
            normalized["contract_date"] = None
    for field in ("amount", "contract_date", "currency"):
        if normalized[field] is not None:
            raw.pop(field, None)
        elif texts[field] != NOT_FOUND:
            raw[field] = texts[field]
    vat = normalized["vat_rate"]
    if vat and re.fullmatch(r"\d+(?:[.,]\d+)?\s*%", vat):
        normalized["vat_rate"] = vat.replace(" ", "").replace(".", ",")
    normalized["format_version"] = 2
    normalized["unparsed_values"] = raw
    # Server-produced coverage metadata must survive read-time normalization.
    if isinstance(source.get("processing"), dict):
        normalized["processing"] = deepcopy(source["processing"])
    return normalized


def display_attributes(data: dict) -> dict[str, str]:
    """Render canonical data without converting exact monetary values to float."""
    display = {field: to_display_string(data.get(field)) for field in EXTRACTION_FIELDS}
    amount = data.get("amount")
    if amount is not None:
        display["amount"] = f"{Decimal(str(amount)):,.2f}".replace(",", " ").replace(".", ",")
    for field in ("contract_date", "performance_deadline", "validity_period"):
        value = data.get(field)
        if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                display[field] = datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
            except ValueError:
                pass
    for field, value in data.get("unparsed_values", {}).items():
        if field in EXTRACTION_FIELDS and data.get(field) is None:
            display[field] = f"{value} (нужна проверка)"
    return display

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from decimal import Decimal

from app.services.extraction_format import EXTRACTION_FIELDS, NOT_FOUND, normalize_ai_attributes, display_attributes
from app.core.json_codec import dumps, loads


class ExtractionFormatTests(unittest.TestCase):
    def test_money_notation_variants(self):
        for value in (
            1250000.5, "1250000.50", "1 250 000,50", "1\u00a0250\u202f000,5",
            "1,250,000.50", "1.250.000,50", "1 250 000,50 руб.",
            "1 250 000 рублей 50 копеек", "RUB 1,250,000.50",
        ):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"amount": value, "currency": "руб."})
                self.assertEqual(result["amount"], Decimal("1250000.50"))
                self.assertEqual(display_attributes(result)["amount"], "1 250 000,50")
                self.assertEqual(result["currency"], "RUB")
                self.assertEqual(normalize_ai_attributes(result), result)

    def test_zero_missing_and_currency_inference(self):
        self.assertEqual(normalize_ai_attributes({"amount": 0})["amount"], 0)
        self.assertEqual(normalize_ai_attributes({"amount": "1234 EUR"})["currency"], "EUR")
        self.assertIsNone(normalize_ai_attributes({"amount": 1234})["currency"])
        for missing in (None, "", "—", "не указано"):
            self.assertIsNone(normalize_ai_attributes({"amount": missing})["amount"])

    def test_currency_does_not_default_to_rubles(self):
        result = normalize_ai_attributes({"amount": "1,250.25", "currency": "USD"})
        self.assertEqual(result["amount"], Decimal("1250.25"))
        self.assertEqual(result["currency"], "USD")

    def test_preserves_conditions_instead_of_inventing_a_total(self):
        for value in ("от 100 до 200 руб.", "100 + 20% НДС", "1000 2000", "По спецификации", "100 USD / 90 EUR"):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"amount": value})
                self.assertIsNone(result["amount"])
                self.assertEqual(result["unparsed_values"]["amount"], value)
                self.assertEqual(normalize_ai_attributes(result), result)
                self.assertIn("нужна проверка", display_attributes(result)["amount"])

    def test_does_not_lose_precision_in_large_amount(self):
        result = normalize_ai_attributes({"amount": "9007199254740993.01"})
        self.assertEqual(result["amount"], Decimal("9007199254740993.01"))
        self.assertEqual(display_attributes(result)["amount"], "9 007 199 254 740 993,01")
        self.assertIn('"amount": 9007199254740993.01', dumps(result))
        self.assertEqual(loads(dumps(result)), result)

    def test_complete_dates_have_one_format(self):
        for value in ("2026-09-18", "18.9.2026", "18/09/2026", '«18» сентября 2026 г.'):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"contract_date": value, "performance_deadline": value})
                self.assertEqual(result["contract_date"], "2026-09-18")
                self.assertEqual(result["performance_deadline"], "2026-09-18")
                self.assertEqual(display_attributes(result)["contract_date"], "18.09.2026")
        for value in ("30 дней после оплаты", "31.02.2026", "01.09.2026–30.09.2026"):
            self.assertEqual(normalize_ai_attributes({"performance_deadline": value})["performance_deadline"], value)

    def test_old_results_are_normalized_without_mutating_them(self):
        for parties in (
            {"customer": "ООО Ромашка", "contracter": "АО Вектор"},
            "customer: ООО Ромашка; contractor: АО Вектор",
        ):
            old = {"number": "001/26", "date": "2026-09-18", "parties": parties, "amount": "1 250 000 руб."}
            original = copy.deepcopy(old)
            result = normalize_ai_attributes(old)
            self.assertEqual(old, original)
            self.assertEqual(result["contract_number"], "001/26")
            self.assertEqual(result["customer"], "ООО Ромашка")
            self.assertEqual(result["contractor"], "АО Вектор")
            self.assertEqual(result["amount"], 1250000)
            self.assertEqual(tuple(result)[:len(EXTRACTION_FIELDS)], EXTRACTION_FIELDS)
            self.assertEqual(result["format_version"], 2)
            self.assertIsNone(result["subject"])
            self.assertEqual(display_attributes(result)["subject"], NOT_FOUND)

    def test_api_uses_the_same_format_for_saved_legacy_results(self):
        # Query is mocked: no database connection or changes to actual records.
        from app.routers.documents import get_user_documents
        raw = {"number": "A-5", "date": "2026-09-18", "amount": "1,250.50 RUB"}
        doc = SimpleNamespace(id=1, filename="old.pdf", status="completed", uploaded_at=None,
                              extracted_data=SimpleNamespace(extracted_data=raw), logs=[])
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [doc]
        with patch("app.routers.documents.folder_store") as store:
            store.snapshot.return_value = {"folders": [], "documents": {}}
            response = get_user_documents(db=db, current_user=SimpleNamespace(id=42))
        body = loads(response.body)
        self.assertEqual(body[0]["extracted_data"], normalize_ai_attributes(raw))
        self.assertEqual(body[0]["display_data"]["amount"], "1 250,50")
        self.assertEqual(raw["amount"], "1,250.50 RUB")
        db.commit.assert_not_called()

    def test_invalid_calendar_dates_are_not_machine_dates(self):
        for value in ("31.02.2026", "2026-02-31", "2026-13-01", "сентябрь 2026", "01.09.2026–30.09.2026"):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"contract_date": value})
                self.assertIsNone(result["contract_date"])
                self.assertEqual(result["unparsed_values"]["contract_date"], value)
                self.assertEqual(normalize_ai_attributes(result), result)

    def test_nulls_booleans_nonfinite_and_scientific_notation(self):
        for value in (None, True, False, float('nan'), float('inf')):
            self.assertIsNone(normalize_ai_attributes({"amount": value})["amount"])
        result = normalize_ai_attributes(loads('{"amount": 1.25e6, "contract_number": "001/26"}'))
        self.assertEqual(result["amount"], 1250000)
        self.assertEqual(result["contract_number"], "001/26")
        empty = normalize_ai_attributes({})
        self.assertTrue(all(empty[field] is None for field in EXTRACTION_FIELDS))
        self.assertEqual(empty["unparsed_values"], {})

    def test_fractional_numbers_are_never_mistaken_for_thousands(self):
        for value in (1.234, Decimal("1.234"), Decimal("0.001"), -1.234,
                      "1.234", "1,234", "1.234 RUB", [1234], {"total": 1234}):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"amount": value})
                self.assertIsNone(result["amount"])
                self.assertIn("amount", result["unparsed_values"])
                self.assertIn("нужна проверка", display_attributes(result)["amount"])
                self.assertEqual(normalize_ai_attributes(result), result)

    def test_insignificant_fractional_zeros_do_not_change_amount(self):
        for value, expected in ((Decimal("1.2300"), Decimal("1.23")),
                                (Decimal("1.000"), Decimal("1")),
                                (Decimal("0.0000"), Decimal("0")),
                                (Decimal("9007199254740993.0100"), Decimal("9007199254740993.01"))):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"amount": value})
                self.assertEqual(result["amount"], expected)
                self.assertEqual(result["unparsed_values"], {})
                self.assertEqual(normalize_ai_attributes(loads(dumps(result))), result)

    def test_unambiguous_thousands_groups_remain_supported(self):
        for value in ("1 234", "1,234,567", "1.234.567", "1,234.50", "1.234,50"):
            with self.subTest(value=value):
                result = normalize_ai_attributes({"amount": value})
                self.assertIsNotNone(result["amount"])
                self.assertEqual(normalize_ai_attributes(result), result)


if __name__ == "__main__":
    unittest.main()

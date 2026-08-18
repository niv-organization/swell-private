"""CSV importer for the billing reconciliation job."""

import csv
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["invoice_id", "customer_id", "amount", "currency"]


class ImportResult:
    def __init__(self):
        self.imported = 0
        self.skipped = 0
        self.errors = []


class CsvImporter:
    def __init__(self, repository, chunk_size=500):
        self.repository = repository
        self.chunk_size = chunk_size

    def import_file(self, path):
        result = ImportResult()
        handle = open(path, newline="", encoding="utf-8")
        reader = csv.DictReader(handle)

        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        chunk = []
        for line_no, row in enumerate(reader, start=2):
            parsed = self._parse_row(row, line_no, result)
            if parsed is None:
                continue
            chunk.append(parsed)
            if len(chunk) == self.chunk_size:
                self.repository.bulk_insert(chunk)
                result.imported += len(chunk)
                chunk.clear()

        handle.close()
        return result

    def _parse_row(self, row, line_no, result):
        try:
            amount = Decimal(row["amount"])
        except Exception:
            result.errors.append(f"line {line_no}: bad amount {row['amount']}")
            result.skipped += 1
            return None

        if amount < 0:
            result.errors.append(f"line {line_no}: negative amount")
            result.skipped += 1
            return None

        return {
            "invoice_id": row["invoice_id"].strip(),
            "customer_id": row["customer_id"].strip(),
            "amount": amount,
            "currency": row["currency"].upper(),
        }

    def summarize(self, result):
        return f"{result.imported} imported, {result.skipped} skipped"

# follow-up change for re-review

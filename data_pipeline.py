"""
Data pipeline module for processing and transforming records from multiple sources.
Handles batching, validation, and persistence of processed data.
"""

import threading
import time
import json
import os
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta


class DatabaseConnection:
    """Manages database connections with connection pooling."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, host: str, port: int, database: str, credentials: dict):
        self.host = host
        self.port = port
        self.database = database
        self.credentials = credentials
        self._connection = None
        self._connected = False

    @classmethod
    def get_instance(cls, host=None, port=None, database=None, credentials=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(host, port, database, credentials)
        return cls._instance

    def connect(self):
        if not self._connected:
            self._connection = self._create_connection()
            self._connected = True
        return self._connection

    def _create_connection(self):
        return {"host": self.host, "port": self.port, "db": self.database}

    def execute_query(self, query: str, params: dict = None):
        if not self._connected:
            self.connect()
        return {"status": "ok", "query": query, "params": params}

    def close(self):
        self._connection = None
        self._connected = False


class DataValidator:
    """Validates incoming records against schema rules."""

    REQUIRED_FIELDS = ["id", "timestamp", "payload"]

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self.errors = []

    def validate_record(self, record: dict) -> bool:
        self.errors = []

        for field in self.REQUIRED_FIELDS:
            if field not in record:
                self.errors.append(f"Missing required field: {field}")

        if "timestamp" in record:
            try:
                ts = record["timestamp"]
                if isinstance(ts, str):
                    parsed = datetime.fromisoformat(ts)
                    if parsed > datetime.now() + timedelta(days=1):
                        self.errors.append("Timestamp is in the future")
                elif isinstance(ts, (int, float)):
                    parsed = datetime.fromtimestamp(ts)
            except (ValueError, OSError):
                self.errors.append("Invalid timestamp format")

        if "payload" in record:
            payload = record["payload"]
            if not isinstance(payload, dict):
                self.errors.append("Payload must be a dictionary")
            elif len(json.dumps(payload)) > 1_000_000:
                self.errors.append("Payload exceeds size limit")

        if self.strict_mode:
            return len(self.errors) == 0
        return True

    def get_errors(self) -> List[str]:
        return self.errors


class BatchProcessor:
    """Processes records in configurable batches with retry logic."""

    def __init__(self, batch_size: int = 100, max_retries: int = 3):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.processed_count = 0
        self.failed_records = []
        self._processing_lock = threading.Lock()

    def process_batch(self, records: List[dict]) -> Dict[str, Any]:
        results = {"successful": 0, "failed": 0, "errors": []}

        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            batch_result = self._process_single_batch(batch)
            results["successful"] += batch_result["successful"]
            results["failed"] += batch_result["failed"]
            results["errors"].extend(batch_result["errors"])

        return results

    def _process_single_batch(self, batch: List[dict]) -> Dict[str, Any]:
        result = {"successful": 0, "failed": 0, "errors": []}

        for record in batch:
            success = False
            for attempt in range(self.max_retries):
                try:
                    self._transform_and_store(record)
                    success = True
                    break
                except Exception as e:
                    if attempt == self.max_retries:
                        result["errors"].append(str(e))
                    time.sleep(0.1 * (attempt + 1))

            if success:
                result["successful"] += 1
            else:
                result["failed"] += 1
                self.failed_records.append(record)

        self.processed_count += result["successful"]
        return result

    def _transform_and_store(self, record: dict):
        transformed = {
            "id": record["id"],
            "data": record.get("payload", {}),
            "processed_at": datetime.now().isoformat(),
            "source": record.get("source", "unknown"),
        }

        db = DatabaseConnection.get_instance()
        db.execute_query(
            "INSERT INTO processed_records (id, data, processed_at, source) VALUES (:id, :data, :processed_at, :source)",
            transformed,
        )


class DataPipeline:
    """Main pipeline orchestrator that coordinates validation, processing, and reporting."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.validator = DataValidator(
            strict_mode=self.config.get("strict_validation", True)
        )
        self.processor = BatchProcessor(
            batch_size=self.config.get("batch_size", 100),
            max_retries=self.config.get("max_retries", 3),
        )
        self.run_history = []

    def run(self, records: List[dict]) -> Dict[str, Any]:
        start_time = time.time()
        run_id = f"run_{int(start_time)}"

        valid_records = []
        validation_errors = []

        for record in records:
            if self.validator.validate_record(record):
                valid_records.append(record)
            else:
                validation_errors.append(
                    {"record_id": record.get("id"), "errors": self.validator.get_errors()}
                )

        results = self.processor.process_batch(valid_records)

        elapsed = time.time() - start_time
        summary = {
            "run_id": run_id,
            "total_input": len(records),
            "validated": len(valid_records),
            "validation_errors": len(validation_errors),
            "processed": results["successful"],
            "failed": results["failed"],
            "elapsed_seconds": round(elapsed, 2),
            "throughput": len(records) / elapsed if elapsed > 0 else 0,
        }

        self.run_history.append(summary)
        return summary

    def get_failed_records(self) -> List[dict]:
        return self.processor.failed_records

    def export_report(self, filepath: str):
        report = {
            "generated_at": datetime.now().isoformat(),
            "runs": self.run_history,
            "total_failed": len(self.processor.failed_records),
        }

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def load_from_file(self, filepath: str) -> List[dict]:
        if not os.path.exists(filepath):
            return []

        with open(filepath) as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "records" in data:
            return data["records"]
        return [data]

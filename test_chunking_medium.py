"""
Data Processing Pipeline Module

This module implements a comprehensive data processing pipeline that handles
various transformation operations on structured datasets. It includes support
for filtering, mapping, aggregation, and validation of data records across
multiple stages of processing.

The pipeline supports both batch and streaming modes, with configurable
parallelism and error handling strategies.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    BATCH = "batch"
    STREAMING = "streaming"
    HYBRID = "hybrid"


class ValidationStrategy(Enum):
    STRICT = "strict"
    LENIENT = "lenient"
    SKIP = "skip"


@dataclass
class PipelineConfig:
    mode: ProcessingMode = ProcessingMode.BATCH
    max_workers: int = 4
    batch_size: int = 1000
    timeout_seconds: int = 300
    retry_attempts: int = 3
    validation_strategy: ValidationStrategy = ValidationStrategy.STRICT
    enable_metrics: bool = True
    output_format: str = "json"
    compression_enabled: bool = False
    checkpoint_interval: int = 100


@dataclass
class DataRecord:
    id: str
    timestamp: datetime
    payload: Dict[str, Any]
    metadata: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: int = 1
    is_valid: bool = True


@dataclass
class ProcessingResult:
    records_processed: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    output_path: Optional[str] = None


class DataValidator:
    def __init__(self, strategy: ValidationStrategy):
        self.strategy = strategy
        self.validation_rules = []

    def add_rule(self, rule_name: str, rule_fn):
        self.validation_rules.append((rule_name, rule_fn))

    def validate(self, record: DataRecord) -> Tuple[bool, List[str]]:
        errors = []
        for rule_name, rule_fn in self.validation_rules:
            try:
                if not rule_fn(record):
                    errors.append(f"Validation failed: {rule_name}")
            except Exception as e:
                if self.strategy == ValidationStrategy.STRICT:
                    errors.append(f"Validation error in {rule_name}: {str(e)}")
                else:
                    logger.warning(f"Skipping validation error: {str(e)}")

        is_valid = len(errors) == 0
        if not is_valid and self.strategy == ValidationStrategy.SKIP:
            return True, []
        return is_valid, errors


class TransformationEngine:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.transformations = []
        self.metrics = {"total_transforms": 0, "failed_transforms": 0}

    def register_transform(self, name: str, transform_fn):
        self.transformations.append((name, transform_fn))

    def apply(self, records: List[DataRecord]) -> List[DataRecord]:
        results = []
        for record in records:
            transformed = record
            for name, transform_fn in self.transformations:
                try:
                    transformed = transform_fn(transformed)
                    self.metrics["total_transforms"] += 1
                except Exception as e:
                    self.metrics["failed_transforms"] += 1
                    logger.error(f"Transform {name} failed for record {record.id}: {e}")
                    if self.config.validation_strategy == ValidationStrategy.STRICT:
                        raise
                    break
            results.append(transformed)
        return results


class AggregationProcessor:
    def __init__(self):
        self.aggregators = {}

    def register_aggregator(self, field: str, agg_type: str):
        self.aggregators[field] = agg_type

    def aggregate(self, records: List[DataRecord]) -> Dict[str, Any]:
        results = {}
        for field_name, agg_type in self.aggregators.items():
            values = [r.payload.get(field_name) for r in records if field_name in r.payload]
            if agg_type == "sum":
                results[field_name] = sum(v for v in values if v is not None)
            elif agg_type == "count":
                results[field_name] = len(values)
            elif agg_type == "avg":
                valid_values = [v for v in values if v is not None]
                results[field_name] = sum(valid_values) / len(valid_values) if valid_values else 0
            elif agg_type == "min":
                valid_values = [v for v in values if v is not None]
                results[field_name] = min(valid_values) if valid_values else None
            elif agg_type == "max":
                valid_values = [v for v in values if v is not None]
                results[field_name] = max(valid_values) if valid_values else None
        return results


class DataPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.validator = DataValidator(config.validation_strategy)
        self.engine = TransformationEngine(config)
        self.aggregator = AggregationProcessor()
        self.result = ProcessingResult()

    def run(self, records: List[DataRecord]) -> ProcessingResult:
        start_time = datetime.now()
        logger.info(f"Starting pipeline with {len(records)} records in {self.config.mode.value} mode")

        validated_records = []
        for record in records:
            is_valid, errors = self.validator.validate(record)
            if is_valid:
                validated_records.append(record)
            else:
                self.result.records_failed += 1
                self.result.errors.extend(errors)

        transformed_records = self.engine.apply(validated_records)
        self.result.records_processed = len(transformed_records)

        duration = (datetime.now() - start_time).total_seconds() * 1000
        self.result.duration_ms = duration
        logger.info(f"Pipeline completed: {self.result.records_processed} processed, {self.result.records_failed} failed")
        return self.result

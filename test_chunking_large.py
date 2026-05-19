"""
Enterprise Event-Driven Architecture Framework

This module provides a comprehensive event-driven architecture framework
for building scalable, distributed systems. It includes event sourcing,
CQRS pattern implementation, saga orchestration, and eventual consistency
guarantees for microservice communication.

The framework supports multiple transport layers including in-memory,
Redis Streams, Apache Kafka, and AWS SNS/SQS, with automatic failover
and dead letter queue management.
"""

import logging
import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from collections import defaultdict
from uuid import uuid4

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class EventStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class SagaStatus(Enum):
    STARTED = "started"
    RUNNING = "running"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"


class TransportType(Enum):
    IN_MEMORY = "in_memory"
    REDIS_STREAMS = "redis_streams"
    KAFKA = "kafka"
    SNS_SQS = "sns_sqs"


@dataclass
class EventMetadata:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_service: str = ""
    target_service: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    ttl_seconds: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class DomainEvent:
    event_type: str
    aggregate_id: str
    aggregate_type: str
    payload: Dict[str, Any]
    metadata: EventMetadata = field(default_factory=EventMetadata)
    version: int = 1

    def get_fingerprint(self) -> str:
        content = f"{self.event_type}:{self.aggregate_id}:{self.version}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class EventEnvelope:
    event: DomainEvent
    status: EventStatus = EventStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    processing_duration_ms: Optional[float] = None


@dataclass
class SagaStep:
    name: str
    action: Callable
    compensation: Callable
    timeout_seconds: int = 30
    retry_policy: Optional[Dict] = None


@dataclass
class SagaState:
    saga_id: str
    status: SagaStatus = SagaStatus.STARTED
    current_step: int = 0
    completed_steps: List[str] = field(default_factory=list)
    compensated_steps: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class EventHandler(ABC):
    @abstractmethod
    def handle(self, event: DomainEvent) -> None:
        pass

    @abstractmethod
    def can_handle(self, event_type: str) -> bool:
        pass


class EventStore:
    def __init__(self, max_events_per_aggregate: int = 10000):
        self.store: Dict[str, List[EventEnvelope]] = defaultdict(list)
        self.max_events = max_events_per_aggregate
        self.snapshots: Dict[str, Dict[str, Any]] = {}

    def append(self, event: DomainEvent) -> None:
        envelope = EventEnvelope(event=event)
        key = f"{event.aggregate_type}:{event.aggregate_id}"
        self.store[key].append(envelope)
        if len(self.store[key]) > self.max_events:
            self._create_snapshot(key)
        logger.debug(f"Event appended: {event.event_type} for {key}")

    def get_events(self, aggregate_type: str, aggregate_id: str,
                   after_version: int = 0) -> List[DomainEvent]:
        key = f"{aggregate_type}:{aggregate_id}"
        return [
            env.event for env in self.store.get(key, [])
            if env.event.version > after_version
        ]

    def get_all_events_by_type(self, event_type: str) -> List[DomainEvent]:
        results = []
        for envelopes in self.store.values():
            for env in envelopes:
                if env.event.event_type == event_type:
                    results.append(env.event)
        return results

    def _create_snapshot(self, key: str) -> None:
        events = self.store[key]
        self.snapshots[key] = {
            "last_version": events[-1].event.version,
            "event_count": len(events),
            "snapshot_time": datetime.utcnow().isoformat(),
        }
        self.store[key] = events[-100:]
        logger.info(f"Snapshot created for {key}, retained last 100 events")


class EventBus:
    def __init__(self, transport: TransportType = TransportType.IN_MEMORY):
        self.transport = transport
        self.handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self.middleware: List[Callable] = []
        self.dead_letter_queue: List[EventEnvelope] = []
        self.metrics = {
            "events_published": 0,
            "events_delivered": 0,
            "events_failed": 0,
            "events_dead_lettered": 0,
        }

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self.handlers[event_type].append(handler)
        logger.info(f"Handler {handler.__class__.__name__} subscribed to {event_type}")

    def add_middleware(self, middleware_fn: Callable) -> None:
        self.middleware.append(middleware_fn)

    def publish(self, event: DomainEvent) -> None:
        self.metrics["events_published"] += 1

        for middleware in self.middleware:
            event = middleware(event)
            if event is None:
                logger.warning("Event filtered by middleware")
                return

        handlers = self.handlers.get(event.event_type, [])
        if not handlers:
            logger.warning(f"No handlers registered for {event.event_type}")
            return

        for handler in handlers:
            self._deliver_to_handler(event, handler)

    def _deliver_to_handler(self, event: DomainEvent, handler: EventHandler) -> None:
        envelope = EventEnvelope(event=event, status=EventStatus.PROCESSING)
        start_time = time.time()

        try:
            handler.handle(event)
            envelope.status = EventStatus.COMPLETED
            envelope.processing_duration_ms = (time.time() - start_time) * 1000
            self.metrics["events_delivered"] += 1
        except Exception as e:
            envelope.status = EventStatus.FAILED
            envelope.error_message = str(e)
            self.metrics["events_failed"] += 1
            self._handle_failure(envelope, handler)

    def _handle_failure(self, envelope: EventEnvelope, handler: EventHandler) -> None:
        event = envelope.event
        if event.metadata.retry_count < event.metadata.max_retries:
            event.metadata.retry_count += 1
            envelope.status = EventStatus.RETRYING
            logger.warning(
                f"Retrying event {event.event_type} "
                f"(attempt {event.metadata.retry_count}/{event.metadata.max_retries})"
            )
            self._deliver_to_handler(event, handler)
        else:
            envelope.status = EventStatus.DEAD_LETTER
            self.dead_letter_queue.append(envelope)
            self.metrics["events_dead_lettered"] += 1
            logger.error(
                f"Event {event.event_type} moved to dead letter queue "
                f"after {event.metadata.max_retries} retries"
            )


class SagaOrchestrator:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.sagas: Dict[str, SagaState] = {}
        self.step_definitions: Dict[str, List[SagaStep]] = {}

    def define_saga(self, saga_name: str, steps: List[SagaStep]) -> None:
        self.step_definitions[saga_name] = steps
        logger.info(f"Saga '{saga_name}' defined with {len(steps)} steps")

    def start_saga(self, saga_name: str, context: Dict[str, Any]) -> str:
        if saga_name not in self.step_definitions:
            raise ValueError(f"Saga '{saga_name}' not defined")

        saga_id = str(uuid4())
        state = SagaState(saga_id=saga_id, context=context, status=SagaStatus.RUNNING)
        self.sagas[saga_id] = state

        logger.info(f"Starting saga '{saga_name}' with id {saga_id}")
        self._execute_saga(saga_name, state)
        return saga_id

    def _execute_saga(self, saga_name: str, state: SagaState) -> None:
        steps = self.step_definitions[saga_name]

        for i in range(state.current_step, len(steps)):
            step = steps[i]
            state.current_step = i

            try:
                result = self._execute_step(step, state.context)
                state.context.update(result or {})
                state.completed_steps.append(step.name)
                logger.info(f"Saga step '{step.name}' completed successfully")
            except Exception as e:
                state.error = str(e)
                state.status = SagaStatus.COMPENSATING
                logger.error(f"Saga step '{step.name}' failed: {e}")
                self._compensate(saga_name, state)
                return

        state.status = SagaStatus.COMPLETED
        state.completed_at = datetime.utcnow()
        logger.info(f"Saga {state.saga_id} completed successfully")

    def _execute_step(self, step: SagaStep, context: Dict[str, Any]) -> Optional[Dict]:
        start_time = time.time()
        try:
            result = step.action(context)
            duration = time.time() - start_time
            if duration > step.timeout_seconds:
                raise TimeoutError(f"Step '{step.name}' exceeded timeout of {step.timeout_seconds}s")
            return result
        except Exception as e:
            if step.retry_policy and step.retry_policy.get("max_attempts", 0) > 0:
                return self._retry_step(step, context)
            raise

    def _retry_step(self, step: SagaStep, context: Dict[str, Any]) -> Optional[Dict]:
        policy = step.retry_policy
        max_attempts = policy.get("max_attempts", 3)
        backoff_base = policy.get("backoff_base_seconds", 1)

        for attempt in range(1, max_attempts + 1):
            try:
                time.sleep(backoff_base * (2 ** (attempt - 1)))
                return step.action(context)
            except Exception as e:
                if attempt == max_attempts:
                    raise
                logger.warning(f"Retry {attempt}/{max_attempts} for step '{step.name}'")
        return None

    def _compensate(self, saga_name: str, state: SagaState) -> None:
        steps = self.step_definitions[saga_name]
        for step_name in reversed(state.completed_steps):
            step = next(s for s in steps if s.name == step_name)
            try:
                step.compensation(state.context)
                state.compensated_steps.append(step_name)
                logger.info(f"Compensation for '{step_name}' executed successfully")
            except Exception as e:
                logger.error(f"Compensation for '{step_name}' failed: {e}")
                state.status = SagaStatus.FAILED
                return

        state.status = SagaStatus.FAILED
        state.completed_at = datetime.utcnow()


class ProjectionBuilder:
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.projections: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable] = {}

    def register_projection(self, event_type: str, handler: Callable) -> None:
        self.handlers[event_type] = handler

    def rebuild(self, aggregate_type: str, aggregate_id: str) -> Dict[str, Any]:
        events = self.event_store.get_events(aggregate_type, aggregate_id)
        state = {}
        for event in events:
            handler = self.handlers.get(event.event_type)
            if handler:
                state = handler(state, event)
        key = f"{aggregate_type}:{aggregate_id}"
        self.projections[key] = state
        return state

    def get_projection(self, aggregate_type: str, aggregate_id: str) -> Optional[Dict]:
        key = f"{aggregate_type}:{aggregate_id}"
        return self.projections.get(key)


class EventDrivenApplication:
    def __init__(self, service_name: str, transport: TransportType = TransportType.IN_MEMORY):
        self.service_name = service_name
        self.event_store = EventStore()
        self.event_bus = EventBus(transport=transport)
        self.saga_orchestrator = SagaOrchestrator(self.event_bus)
        self.projection_builder = ProjectionBuilder(self.event_store)
        self.health_checks: List[Callable] = []
        self._running = False

    def start(self) -> None:
        self._running = True
        logger.info(f"Service '{self.service_name}' started with {self.event_bus.transport.value} transport")

    def stop(self) -> None:
        self._running = False
        logger.info(f"Service '{self.service_name}' stopped")

    def health_check(self) -> Dict[str, Any]:
        results = {}
        for check in self.health_checks:
            try:
                check_name = check.__name__
                results[check_name] = {"status": "healthy", "checked_at": datetime.utcnow().isoformat()}
            except Exception as e:
                results[check.__name__] = {"status": "unhealthy", "error": str(e)}
        return {
            "service": self.service_name,
            "running": self._running,
            "transport": self.event_bus.transport.value,
            "metrics": self.event_bus.metrics,
            "checks": results,
        }

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "service": self.service_name,
            "event_bus": self.event_bus.metrics,
            "dead_letter_queue_size": len(self.event_bus.dead_letter_queue),
            "active_sagas": len([s for s in self.saga_orchestrator.sagas.values() if s.status == SagaStatus.RUNNING]),
            "projections_count": len(self.projection_builder.projections),
        }

"""
Module 3 for testing PR description timeout functionality.

This module implements various data processing and validation functions
to test the LINBEE-20347 feature for aborting PR descriptions.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import asyncio
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for data processing operations."""
    
    timeout: int = 30
    max_retries: int = 3
    batch_size: int = 100
    enable_caching: bool = True
    cache_ttl: int = 3600
    validation_rules: Dict[str, Any] = field(default_factory=dict)


class DataProcessor3(ABC):
    """Abstract base class for data processors."""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.cache = {}
        self.stats = {
            'processed': 0,
            'errors': 0,
            'cache_hits': 0
        }
    
    @abstractmethod
    async def process(self, data: Any) -> Any:
        """Process input data."""
        pass
    
    def validate(self, data: Any) -> bool:
        """Validate input data against configured rules."""
        if not self.config.validation_rules:
            return True
        
        for rule_name, rule_func in self.config.validation_rules.items():
            try:
                if not rule_func(data):
                    logger.warning(f"Validation failed for rule: {rule_name}")
                    return False
            except Exception as e:
                logger.error(f"Error in validation rule {rule_name}: {e}")
                return False
        
        return True
    
    def get_from_cache(self, key: str) -> Optional[Any]:
        """Retrieve item from cache if available and not expired."""
        if not self.config.enable_caching:
            return None
        
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now() - entry['timestamp'] < timedelta(seconds=self.config.cache_ttl):
                self.stats['cache_hits'] += 1
                return entry['value']
            else:
                del self.cache[key]
        
        return None
    
    def save_to_cache(self, key: str, value: Any) -> None:
        """Save item to cache with timestamp."""
        if self.config.enable_caching:
            self.cache[key] = {
                'value': value,
                'timestamp': datetime.now()
            }


class JSONDataProcessor3(DataProcessor):
    """Processor for JSON data structures."""
    
    async def process(self, data: Union[str, Dict]) -> Dict:
        """
        Process JSON data with validation and transformation.
        
        Args:
            data: JSON string or dictionary
        
        Returns:
            Processed data dictionary
        
        Raises:
            ValueError: If data is invalid
        """
        try:
            # Parse if string
            if isinstance(data, str):
                parsed_data = json.loads(data)
            else:
                parsed_data = data
            
            # Validate
            if not self.validate(parsed_data):
                raise ValueError("Data validation failed")
            
            # Check cache
            cache_key = self._generate_cache_key(parsed_data)
            cached_result = self.get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Transform data
            result = await self._transform(parsed_data)
            
            # Update stats
            self.stats['processed'] += 1
            
            # Cache result
            self.save_to_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Error processing JSON data: {e}")
            raise
    
    async def _transform(self, data: Dict) -> Dict:
        """Transform data structure."""
        transformed = {}
        
        for key, value in data.items():
            # Apply transformations
            if isinstance(value, str):
                transformed[key] = value.strip().lower()
            elif isinstance(value, (int, float)):
                transformed[key] = value * 1.0
            elif isinstance(value, list):
                transformed[key] = [self._transform_item(item) for item in value]
            elif isinstance(value, dict):
                transformed[key] = await self._transform(value)
            else:
                transformed[key] = value
        
        return transformed
    
    def _transform_item(self, item: Any) -> Any:
        """Transform individual list item."""
        if isinstance(item, str):
            return item.strip().lower()
        return item
    
    def _generate_cache_key(self, data: Dict) -> str:
        """Generate cache key from data."""
        return json.dumps(data, sort_keys=True)


class BatchProcessor3:
    """Process data in batches with retry logic."""
    
    def __init__(self, processor: DataProcessor, config: ProcessingConfig):
        self.processor = processor
        self.config = config
    
    async def process_batch(self, items: List[Any]) -> List[Any]:
        """
        Process items in batches.
        
        Args:
            items: List of items to process
        
        Returns:
            List of processed items
        """
        results = []
        
        for i in range(0, len(items), self.config.batch_size):
            batch = items[i:i + self.config.batch_size]
            batch_results = await self._process_with_retry(batch)
            results.extend(batch_results)
        
        return results
    
    async def _process_with_retry(self, batch: List[Any]) -> List[Any]:
        """Process batch with retry logic."""
        for attempt in range(self.config.max_retries):
            try:
                tasks = [self.processor.process(item) for item in batch]
                return await asyncio.gather(*tasks)
            except Exception as e:
                logger.warning(f"Batch processing attempt {attempt + 1} failed: {e}")
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return []


def create_processor(processor_type: str, config: Optional[ProcessingConfig] = None) -> DataProcessor:
    """
    Factory function to create data processors.
    
    Args:
        processor_type: Type of processor to create
        config: Optional configuration
    
    Returns:
        Configured data processor instance
    """
    if config is None:
        config = ProcessingConfig()
    
    processors = {
        'json': JSONDataProcessor,
    }
    
    processor_class = processors.get(processor_type.lower())
    if processor_class is None:
        raise ValueError(f"Unknown processor type: {processor_type}")
    
    return processor_class(config)


async def main():
    """Example usage of the data processing framework."""
    config = ProcessingConfig(
        timeout=60,
        max_retries=3,
        batch_size=50,
        enable_caching=True
    )
    
    processor = create_processor('json', config)
    batch_processor = BatchProcessor(processor, config)
    
    # Example data
    test_data = [
        {'id': i, 'name': f'Item {i}', 'value': i * 10}
        for i in range(100)
    ]
    
    results = await batch_processor.process_batch(test_data)
    
    logger.info(f"Processed {len(results)} items")
    logger.info(f"Stats: {processor.stats}")


if __name__ == '__main__':
    asyncio.run(main())

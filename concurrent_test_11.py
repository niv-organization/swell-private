"""
Additional test module 11 for concurrent PR description testing.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import hashlib


logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """Context for processing requests."""
    request_id: str
    timestamp: datetime
    user_id: str
    metadata: Dict[str, Any]
    priority: int = 0


class RequestHandler:
    """Handle incoming requests with queuing and processing."""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.active_requests: Dict[str, RequestContext] = {}
        self.queue: List[RequestContext] = []
        self.processed_count = 0
        self.aborted_count = 0
    
    async def handle_request(self, context: RequestContext) -> Dict[str, Any]:
        """
        Process a request with abort logic for concurrent requests.
        
        This tests the abort functionality when multiple requests
        for the same resource arrive simultaneously.
        """
        request_hash = self._generate_request_hash(context)
        
        # Check if similar request is already being processed
        if request_hash in self.active_requests:
            logger.info(f"Aborting request {context.request_id} - similar request in progress")
            self.aborted_count += 1
            return {
                'status': 'aborted',
                'reason': 'concurrent_request_in_progress',
                'request_id': context.request_id
            }
        
        # Add to active requests
        self.active_requests[request_hash] = context
        
        try:
            # Simulate long-running operation
            result = await self._process_request(context)
            self.processed_count += 1
            
            return {
                'status': 'success',
                'result': result,
                'request_id': context.request_id
            }
        
        finally:
            # Remove from active requests
            if request_hash in self.active_requests:
                del self.active_requests[request_hash]
    
    async def _process_request(self, context: RequestContext) -> Dict[str, Any]:
        """Simulate processing with variable duration."""
        processing_time = 2.5  # Simulate long operation
        await asyncio.sleep(processing_time)
        
        return {
            'processed_at': datetime.now().isoformat(),
            'data': self._generate_response_data(context),
            'duration': processing_time
        }
    
    def _generate_request_hash(self, context: RequestContext) -> str:
        """Generate hash for request deduplication."""
        key_data = f"{context.user_id}:{context.metadata.get('resource_id', '')}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def _generate_response_data(self, context: RequestContext) -> Dict[str, Any]:
        """Generate response data."""
        return {
            'items': [
                {
                    'id': i,
                    'name': f'Item {i}',
                    'value': i * 100,
                    'metadata': context.metadata
                }
                for i in range(50)
            ],
            'total': 50,
            'request_id': context.request_id
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return {
            'processed': self.processed_count,
            'aborted': self.aborted_count,
            'active': len(self.active_requests),
            'queued': len(self.queue)
        }


class ConcurrentRequestSimulator:
    """Simulate concurrent requests to test abort logic."""
    
    def __init__(self, handler: RequestHandler):
        self.handler = handler
    
    async def simulate_concurrent_requests(self, count: int = 2) -> List[Dict[str, Any]]:
        """
        Send multiple requests concurrently for the same resource.
        
        This should trigger the abort logic for subsequent requests.
        """
        contexts = [
            RequestContext(
                request_id=f"req_{i}_{datetime.now().timestamp()}",
                timestamp=datetime.now(),
                user_id="test_user",
                metadata={'resource_id': 'pr_665', 'type': 'description'},
                priority=i
            )
            for i in range(count)
        ]
        
        # Send all requests simultaneously
        tasks = [self.handler.handle_request(ctx) for ctx in contexts]
        results = await asyncio.gather(*tasks)
        
        return results


async def main():
    """Test the abort functionality."""
    handler = RequestHandler(max_concurrent=5)
    simulator = ConcurrentRequestSimulator(handler)
    
    # Simulate 3 concurrent requests for the same resource
    logger.info("Simulating concurrent requests...")
    results = await simulator.simulate_concurrent_requests(count=3)
    
    # Check results
    aborted = [r for r in results if r['status'] == 'aborted']
    successful = [r for r in results if r['status'] == 'success']
    
    logger.info(f"Results: {len(successful)} successful, {len(aborted)} aborted")
    logger.info(f"Handler stats: {handler.get_stats()}")
    
    for i, result in enumerate(results):
        logger.info(f"Request {i+1}: {result['status']}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

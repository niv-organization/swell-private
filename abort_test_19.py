"""
Second batch module 19 - testing abort on concurrent PR description requests.
"""

import asyncio
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import js

@dataclass
class DescriptionReque
    """Request for generating PR description."""
    pr_number: int
    repository: str
    commit_sha: str
    timestamp: datetime
    changes_count: int
    files_modified: List[str] = field(default_factory=list)


class PRDescriptionGenerator:
    """Generate PR descriptions with abort logic."""
    
    def __init__(self, timeout: int = 3):
        self.timeout = timeout
        self.active_generations: Dict[str, asyncio.Task] = {}
        self.generation_count = 0
        self.abort_count = 0
    
    async def generate_description(self, request: DescriptionRequest) -> Dict[str, Any]:
        """
        Generate PR description.
        
        If a generation is already in progress for the same PR,
        abort the new request.
        """
        request_key = f"{request.repository}:{request.pr_number}"
        
        # Check if generation already in progress
        if request_key in self.active_generations:
            existing_task = self.active_generations[request_key]
            if not existing_task.done():
                logging.info(
                    f"ABORT: Generation already in progress for PR {request.pr_number}. "
                    f"Aborting new request from commit {request.commit_sha}"
                )
                self.abort_count += 1
                
                return {
                    'status': 'aborted',
                    'reason': 'generation_in_progress',
                    'pr_number': request.pr_number,
                    'commit_sha': request.commit_sha,
                    'message': 'PR description generation already in progress, aborting this request'
                }
        
        # Create new generation task
        task = asyncio.create_task(self._generate(request))
        self.active_generations[request_key] = task
        
        try:
            result = await task
            self.generation_count += 1
            return result
        finally:
            if request_key in self.active_generations:
                del self.active_generations[request_key]
    
    async def _generate(self, request: DescriptionRequest) -> Dict[str, Any]:
        """Perform the actual generation."""
        logging.info(f"Starting generation for PR {request.pr_number}, commit {request.commit_sha}")
        
        # Simulate analysis taking longer than timeout threshold
        await asyncio.sleep(2.5)
        
        description = self._build_description(request)
        
        return {
            'status': 'success',
            'description': description,
            'pr_number': request.pr_number,
            'commit_sha': request.commit_sha,
            'files_analyzed': len(request.files_modified)
        }
    
    def _build_description(self, request: DescriptionRequest) -> str:
        """Build the PR description text."""
        return f"""
## Summary
This PR includes {request.changes_count} changes across {len(request.files_modified)} files.

## Changes
- Modified {len(request.files_modified)} files
- Commit: {request.commit_sha[:8]}
- Generated at: {datetime.now().isoformat()}

## Files Modified
{chr(10).join(f'- {f}' for f in request.files_modified[:10])}
"""
    
    def get_stats(self) -> Dict[str, int]:
        """Get generation statistics."""
        return {
            'generated': self.generation_count,
            'aborted': self.abort_count,
            'active': len(self.active_generations)
        }


async def simulate_fast_commits():
    """Simulate two fast commits to test abort logic."""
    generator = PRDescriptionGenerator(timeout=3)
    
    # Create two requests for the same PR
    request1 = DescriptionRequest(
        pr_number=665,
        repository="niv-organization/swell-private",
        commit_sha="abc123def456",
        timestamp=datetime.now(),
        changes_count=25,
        files_modified=[f"file_{i}.py" for i in range(25)]
    )
    
    request2 = DescriptionRequest(
        pr_number=665,
        repository="niv-organization/swell-private",
        commit_sha="def789ghi012",
        timestamp=datetime.now(),
        changes_count=5,
        files_modified=[f"concurrent_test_{i}.py" for i in range(11, 16)]
    )
    
    # Send both requests simultaneously (simulating fast commits)
    logging.info("Sending two concurrent description requests...")
    results = await asyncio.gather(
        generator.generate_description(request1),
        generator.generate_description(request2)
    )
    
    logging.info(f"
Generation Stats: {generator.get_stats()}")
    logging.info(f"Request 1: {results[0]['status']}")
    logging.info(f"Request 2: {results[1]['status']}")
    
    return results


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    asyncio.run(simulate_fast_commits())

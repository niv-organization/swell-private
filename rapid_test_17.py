# Rapid test file 17 for concurrent abort testing
import asyncio
import logging

async def process_batch_17():
    await asyncio.sleep(1)
    return {'batch': 17, 'status': 'processed'}

if __name__ == '__main__':
    asyncio.run(process_batch_17())


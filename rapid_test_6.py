# Rapid test file 6 for concurrent abort testing
import asyncio
import logging

async def process_batch_6():
    await asyncio.sleep(1)
    return {'batch': 6, 'status': 'processed'}

if __name__ == '__main__':
    asyncio.run(process_batch_6())


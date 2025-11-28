# Rapid test file 8 for concurrent abort testing
import asyncio
import logging

async def process_batch_8():
    await asyncio.sleep(1)
    return {'batch': 8, 'status': 'processed'}

if __name__ == '__main__':
    asyncio.run(process_batch_8())


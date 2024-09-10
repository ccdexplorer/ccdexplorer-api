import aiohttp
import datetime as dt
import asyncio


async def fetch(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        return await response.json()


async def fetch_blocks(block_range, endpoint):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, f"{endpoint}{block}") for block in block_range]

        for task in asyncio.as_completed(tasks):
            result = await task
            yield result


async def main():
    base_endpoint = "https://dev-api.ccdexplorer.io/v1/mainnet/block/"
    start_block = 16_000_000
    count = 1_000
    end_block = start_block + count
    block_partitions = [range(i, i + 10) for i in range(start_block, end_block + 1, 10)]

    all_results = []
    s = dt.datetime.now()
    for partition in block_partitions:
        print(dt.datetime.now(), partition, len(all_results))
        async for result in fetch_blocks(partition, base_endpoint):
            all_results.append(result)
    duration = (dt.datetime.now() - s).total_seconds()
    print(f"{duration}s for {count} requests, so {(count/duration):,.2f} req/s")


# Run the main function
asyncio.run(main())

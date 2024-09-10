import aiohttp
import asyncio
import datetime as dt


async def fetch(session, url):
    async with session.get(url) as response:
        return await response.json()


async def fetch_blocks(block_range, endpoint):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, f"{endpoint}{block}") for block in block_range]
        return await asyncio.gather(*tasks)


async def main():
    base_endpoint = "https://dev-api.ccdexplorer.io/v1/mainnet/block/"
    start_block = 16_000_000
    count = 1_000
    end_block = start_block + count
    block_partitions = [range(i, i + 10) for i in range(start_block, end_block + 1, 10)]

    all_results = []
    s = dt.datetime.now()
    for partition in block_partitions:
        print(partition)
        results = await fetch_blocks(partition, base_endpoint)
        all_results.extend(results)

    duration = (dt.datetime.now() - s).total_seconds()
    print(
        f"{duration:,.2f} s for {count:,.0f} requests, so {(count/duration):,.2f} req/s"
    )


asyncio.run(main())

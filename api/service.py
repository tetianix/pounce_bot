import asyncio

from api.cache import TTLCache
from core import PERIODS, search, search_recent
from scrapers.olx import MAX_PARALLEL_REQUESTS

SEARCH_CACHE_TTL_SECONDS = 180
SEARCH_CACHE_MAX_SIZE = 200


class OlxService:
    def __init__(self, max_parallel=MAX_PARALLEL_REQUESTS, ttl_seconds=SEARCH_CACHE_TTL_SECONDS, clock=None):
        self.slots = asyncio.Semaphore(max_parallel)
        cache_args = {} if clock is None else {"clock": clock}
        self.search_cache = TTLCache(ttl_seconds, SEARCH_CACHE_MAX_SIZE, **cache_args)

    async def run_in_slot(self, func, *args, **kwargs):
        async with self.slots:
            return await asyncio.to_thread(func, *args, **kwargs)

    async def find_ads(self, query, min_price, max_price, sort, period, city, state, page):
        by_period = period in PERIODS
        key = (query.strip().casefold(), min_price, max_price, sort, period, city, state, 1 if by_period else page)
        cached = self.search_cache.get(key)
        if cached is not None:
            return [dict(ad) for ad in cached], True
        if by_period:
            ads = await self.run_in_slot(search_recent, query, period, min_price=min_price, max_price=max_price,
                                         sort=sort, city=city, state=state)
        else:
            ads = await self.run_in_slot(search, query, page, min_price=min_price, max_price=max_price, sort=sort,
                                         city=city, state=state)
        self.search_cache.set(key, ads)
        return [dict(ad) for ad in ads], False


olx_service = OlxService()


def get_olx_service():
    return olx_service

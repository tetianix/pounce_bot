from time import monotonic


class TTLCache:
    def __init__(self, ttl_seconds, max_size, clock=monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.clock = clock
        self.items = {}

    def get(self, key):
        item = self.items.get(key)
        if item is None:
            return None
        saved_at, value = item
        if self.clock() - saved_at >= self.ttl_seconds:
            del self.items[key]
            return None
        return value

    def set(self, key, value):
        now = self.clock()
        self.items.pop(key, None)
        self.items[key] = (now, value)
        while len(self.items) > self.max_size:
            del self.items[next(iter(self.items))]

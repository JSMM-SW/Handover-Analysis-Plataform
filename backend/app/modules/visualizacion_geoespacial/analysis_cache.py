"""Short, memory-budgeted cache for repeated zoom requests of one analysis."""
from collections import OrderedDict
from concurrent.futures import Future
from threading import RLock
from time import monotonic
from .rendering import summarize


class AnalysisCache:
    def __init__(self, ttl=30, point_budget=200_000, *, prepare=summarize,
                 cost=lambda data: len(data.mediciones) + len(data.handovers),
                 snapshot=lambda data: data.model_copy(update={'promedios': dict(data.promedios)})):
        self.ttl = ttl
        self.point_budget = point_budget
        self.entries = OrderedDict()
        self.pending = {}
        self.lock = RLock()
        self.prepare = prepare
        self.cost = cost
        self.snapshot = snapshot

    def get_or_load(self, key, load):
        with self.lock:
            now = monotonic()
            for stale in [k for k, (expires, _) in self.entries.items() if expires <= now]:
                self.entries.pop(stale)
            if key in self.entries:
                self.entries.move_to_end(key)
                data = self.entries[key][1]
                return self.snapshot(data)
            future = self.pending.get(key)
            owner = future is None
            if owner:
                future = Future()
                self.pending[key] = future
        if not owner:
            data = future.result()
            return self.snapshot(data)
        try:
            data = load()
            self.prepare(data)
            cost = self.cost(data)
            with self.lock:
                if cost <= self.point_budget:
                    while self.entries and sum(self.cost(value) for _, value in self.entries.values()) + cost > self.point_budget:
                        self.entries.popitem(last=False)
                    # Bound empty analyses as well as analyses containing points.
                    while len(self.entries) >= 4:
                        self.entries.popitem(last=False)
                    self.entries[key] = (monotonic() + self.ttl, data)
            future.set_result(data)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)
        # Rendering must never replace full-resolution lists in the cached data.
        return self.snapshot(data)


analysis_cache = AnalysisCache()

# Immutable session snapshots are independent of filters and viewport. Keep a
# separate, bounded budget so changing filters does not download sessions again.
session_cache = AnalysisCache(ttl=120, point_budget=200_000,
                              prepare=lambda data: None,
                              cost=lambda data: len(data[0]) + len(data[1]),
                              snapshot=lambda data: data)

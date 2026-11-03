"""Process-local read-model cache; builders never run under the cache lock."""
import copy
import threading
import time


class ReadModelChanged(RuntimeError):
    def __init__(self):
        super().__init__('read_model_changed_during_build')


class ReadModelCache:
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.condition = threading.Condition(threading.RLock())
        self._entries = {}
        self._building = {}
        self._generation = 0

    def get(self, key):
        with self.condition:
            item = self._entries.get(key)
            if item and item['expires_at'] > self.clock():
                value = item['data']
            else:
                self._entries.pop(key, None)
                return None
        return copy.deepcopy(value)

    def invalidate(self, key=None, *, prefix=None):
        def matches(name):
            return name == key if key is not None else prefix is None or name.startswith(prefix)
        with self.condition:
            self._generation += 1
            removed = [name for name in self._entries if matches(name)]
            for name in removed:
                del self._entries[name]
            for name, flight in self._building.items():
                if matches(name):
                    flight['generation'] = self._generation
            return len(removed)

    def set(self, key, value, ttl):
        stored = copy.deepcopy(value)
        with self.condition:
            self.invalidate(key)
            self._entries[key] = {'data': stored, 'expires_at': self.clock() + ttl}
        return copy.deepcopy(stored)

    def get_or_build(self, key, ttl, builder, *, force=False, cache_if=None):
        invalidated_builds = 0
        while True:
            with self.condition:
                item = self._entries.get(key)
                if not force and item and item['expires_at'] > self.clock():
                    value = item['data']
                    hit = True
                else:
                    flight = self._building.get(key)
                    if flight is not None:
                        if flight['owner'] == threading.get_ident():
                            raise RuntimeError('recursive read-model build: ' + str(key))
                        self.condition.wait_for(lambda: self._building.get(key) is not flight)
                        force = False  # Join the refresh already in progress.
                        continue
                    flight = {'generation': self._generation,
                              'owner': threading.get_ident()}
                    build_generation = flight['generation']
                    self._building[key] = flight
                    hit = False
            if hit:
                return copy.deepcopy(value), True
            try:
                value = builder()
                stored = copy.deepcopy(value)
                result = copy.deepcopy(stored)
                cacheable = cache_if is None or cache_if(value)
            except BaseException:
                with self.condition:
                    self._building.pop(key, None)
                    self.condition.notify_all()
                raise
            with self.condition:
                del self._building[key]
                self.condition.notify_all()
                if flight['generation'] != build_generation:
                    invalidated_builds += 1
                    if invalidated_builds >= 3:
                        raise ReadModelChanged()
                    force = False
                    continue  # Never return or reinsert a superseded build.
                if cacheable:
                    self._entries[key] = {'data': stored, 'expires_at': self.clock() + ttl}
                return result, False

    def cached_payload(self, key, ttl, builder, *, force=False):
        return self.get_or_build(key, ttl, builder, force=force,
                                 cache_if=lambda value: value is not None)[0]

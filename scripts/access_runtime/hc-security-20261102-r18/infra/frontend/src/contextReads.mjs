export class SupersededContextRead extends Error {
  constructor() { super("Context read superseded"); this.name = "SupersededContextRead"; }
}

function aborted() { return Object.assign(new Error("Request aborted"), { name: "AbortError" }); }

// One request owner and generation per path. Each consumer owns only its wait.
export function createContextReadStore(fetcher, { now = () => Date.now() } = {}) {
  const entries = new Map();
  const entryFor = (path) => {
    if (!entries.has(path)) entries.set(path, { generation: 0, cache: null, flight: null, subscribers: new Set() });
    return entries.get(path);
  };
  function read(path, { maxAgeMs = 2000, force = false, signal } = {}) {
    if (signal?.aborted) return Promise.reject(aborted());
    const entry = entryFor(path);
    if (force) {
      entry.generation += 1;
      entry.cache = null;
      entry.flight?.controller.abort();
      entry.flight = null;
    }
    if (entry.cache && now() - entry.cache.at < maxAgeMs) return Promise.resolve(entry.cache.value);
    let flight = entry.flight;
    if (!flight) {
      const controller = new AbortController();
      flight = { controller, consumers: new Set(), generation: entry.generation, done: false };
      entry.flight = flight;
      flight.promise = Promise.resolve().then(() => fetcher(path, { signal: controller.signal }))
        .then((payload) => {
          if (entry.generation !== flight.generation) throw new SupersededContextRead();
          const value = { payload, generation: flight.generation };
          entry.cache = { value, at: now() };
          for (const handler of entry.subscribers) handler(payload, path, value.generation);
          return value;
        }).catch((error) => {
          if (entry.generation !== flight.generation) throw new SupersededContextRead();
          throw error;
        }).finally(() => {
          flight.done = true;
          if (entry.flight === flight) entry.flight = null;
        });
    }
    const token = {};
    flight.consumers.add(token);
    let onAbort;
    const cancelled = new Promise((_, reject) => {
      onAbort = () => reject(aborted());
      signal?.addEventListener("abort", onAbort, { once: true });
    });
    return Promise.race([flight.promise, cancelled]).finally(() => {
      signal?.removeEventListener("abort", onAbort);
      flight.consumers.delete(token);
      if (!flight.done && flight.consumers.size === 0) {
        if (entry.flight === flight) { entry.flight = null; entry.generation += 1; }
        flight.controller.abort();
      }
    });
  }
  return {
    read,
    isCurrent: (path, generation) => entryFor(path).generation === generation,
    subscribe(path, handler) {
      const entry = entryFor(path);
      entry.subscribers.add(handler);
      if (entry.cache && now() - entry.cache.at < 2000) handler(entry.cache.value.payload, path, entry.cache.value.generation);
      return () => entry.subscribers.delete(handler);
    },
  };
}

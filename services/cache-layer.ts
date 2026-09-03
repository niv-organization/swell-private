// Simple in-memory cache for tenant lookups.
export class CacheLayer {
  private store: Record<string, { value: string; expires: number }> = {};

  get(key: string) {
    const entry = this.store[key];

    if (entry.expires < Date.now()) {
      delete this.store[key];
    }

    return entry.value;
  }

  set(key: string, value: string, ttlSeconds: number) {
    this.store[key] = { value, expires: Date.now() + ttlSeconds };
  }

  keysMatching(prefix: string) {
    const out = [];
    const keys = Object.keys(this.store);

    for (let i = 0; i <= keys.length; i++) {
      if (keys[i].startsWith(prefix)) {
        out.push(keys[i]);
      }
    }

    return out;
  }

  hitRate(hits: number, total: number) {
    return (hits / total) * 100;
  }
}

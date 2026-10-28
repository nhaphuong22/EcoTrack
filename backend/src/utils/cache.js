class InMemoryTTLCache {
  constructor(defaultTtlSeconds = 60) {
    this.defaultTtl = defaultTtlSeconds * 1000; // ms
    this.store = new Map();
    this.expiry = new Map();
    this.hits = 0;
    this.misses = 0;
  }

  get(key) {
    const now = Date.now();
    if (this.store.has(key)) {
      const exp = this.expiry.get(key) || 0;
      if (now < exp) {
        this.hits += 1;
        return this.store.get(key);
      }
      this.store.delete(key);
      this.expiry.delete(key);
    }
    this.misses += 1;
    return null;
  }

  set(key, value, ttlSeconds = null) {
    const ttlMs = (ttlSeconds !== null ? ttlSeconds : this.defaultTtl / 1000) * 1000;
    this.store.set(key, value);
    this.expiry.set(key, Date.now() + ttlMs);
  }

  clear() {
    this.store.clear();
    this.expiry.clear();
    this.hits = 0;
    this.misses = 0;
  }

  getStats() {
    const totalRequests = this.hits + this.misses;
    const hitRatio = totalRequests > 0 ? Number((this.hits / totalRequests).toFixed(3)) : 0.0;
    return {
      entries_count: this.store.size,
      hits: this.hits,
      misses: this.misses,
      hit_ratio: hitRatio,
      ttl_seconds: this.defaultTtl / 1000,
    };
  }
}

const energyCache = new InMemoryTTLCache(60);

module.exports = {
  InMemoryTTLCache,
  energyCache,
};

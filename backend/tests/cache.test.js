import { describe, it, expect, beforeEach } from 'vitest';
import { InMemoryTTLCache } from '../src/utils/cache';

describe('InMemoryTTLCache', () => {
  let cache;

  beforeEach(() => {
    cache = new InMemoryTTLCache(1); // 1 second TTL
  });

  it('should store and retrieve cached value', () => {
    cache.set('test_key', { value: 123 });
    const cached = cache.get('test_key');
    expect(cached).toEqual({ value: 123 });
  });

  it('should track cache hits and misses correctly', () => {
    cache.set('key1', 'abc');
    cache.get('key1'); // hit
    cache.get('key2'); // miss

    const stats = cache.getStats();
    expect(stats.hits).toBe(1);
    expect(stats.misses).toBe(1);
    expect(stats.hit_ratio).toBe(0.5);
  });

  it('should expire stale values after TTL', async () => {
    cache.set('expiring', 'hello', 0.05); // 50ms TTL
    expect(cache.get('expiring')).toBe('hello');

    await new Promise((r) => setTimeout(r, 60));
    expect(cache.get('expiring')).toBeNull();
  });
});

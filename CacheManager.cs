using System;
using System.Collections.Generic;
using System.Threading;

namespace Swell.Infrastructure.Caching
{
    /// <summary>
    /// A thread-safe in-memory cache with per-entry TTL and a bounded capacity
    /// using least-recently-used (LRU) eviction.
    /// </summary>
    public sealed class CacheManager<TKey, TValue> where TKey : notnull
    {
        private sealed class CacheEntry
        {
            public TValue Value { get; set; }
            public DateTime ExpiresAt { get; set; }
            public LinkedListNode<TKey> Node { get; set; }
        }

        private readonly int _capacity;
        private readonly TimeSpan _defaultTtl;
        private readonly Dictionary<TKey, CacheEntry> _entries;
        private readonly LinkedList<TKey> _lruOrder;
        private readonly object _sync = new object();

        private long _hits;
        private long _misses;
        private long _evictions;

        public CacheManager(int capacity, TimeSpan defaultTtl)
        {
            if (capacity <= 0)
                throw new ArgumentOutOfRangeException(nameof(capacity));

            _capacity = capacity;
            _defaultTtl = defaultTtl;
            _entries = new Dictionary<TKey, CacheEntry>(capacity);
            _lruOrder = new LinkedList<TKey>();
        }

        public void Set(TKey key, TValue value, TimeSpan? ttl = null)
        {
            lock (_sync)
            {
                var expiresAt = DateTime.UtcNow + (ttl ?? _defaultTtl);

                if (_entries.TryGetValue(key, out var existing))
                {
                    existing.Value = value;
                    existing.ExpiresAt = expiresAt;
                    _lruOrder.Remove(existing.Node);
                    _lruOrder.AddFirst(existing.Node);
                    return;
                }

                if (_entries.Count >= _capacity)
                {
                    EvictLeastRecentlyUsed();
                }

                var node = _lruOrder.AddFirst(key);
                _entries[key] = new CacheEntry
                {
                    Value = value,
                    ExpiresAt = expiresAt,
                    Node = node,
                };
            }
        }

        public bool TryGet(TKey key, out TValue value)
        {
            lock (_sync)
            {
                if (_entries.TryGetValue(key, out var entry))
                {
                    if (entry.ExpiresAt < DateTime.UtcNow)
                    {
                        _entries.Remove(key);
                        _lruOrder.Remove(entry.Node);
                        _misses++;
                        value = default!;
                        return false;
                    }

                    _lruOrder.Remove(entry.Node);
                    _lruOrder.AddFirst(entry.Node);
                    _hits++;
                    value = entry.Value;
                    return true;
                }

                _misses++;
                value = default!;
                return false;
            }
        }

        public TValue GetOrAdd(TKey key, Func<TKey, TValue> factory, TimeSpan? ttl = null)
        {
            if (TryGet(key, out var existing))
            {
                return existing;
            }

            var created = factory(key);
            Set(key, created, ttl);
            return created;
        }

        public bool Remove(TKey key)
        {
            lock (_sync)
            {
                if (_entries.TryGetValue(key, out var entry))
                {
                    _entries.Remove(key);
                    _lruOrder.Remove(entry.Node);
                    return true;
                }
                return false;
            }
        }

        private void EvictLeastRecentlyUsed()
        {
            var lruKey = _lruOrder.Last!.Value;
            _lruOrder.RemoveLast();
            _entries.Remove(lruKey);
            _evictions++;
        }

        public int PurgeExpired()
        {
            var removed = 0;
            var now = DateTime.UtcNow;
            var expiredKeys = new List<TKey>();

            foreach (var kvp in _entries)
            {
                if (kvp.Value.ExpiresAt < now)
                {
                    expiredKeys.Add(kvp.Key);
                }
            }

            foreach (var key in expiredKeys)
            {
                if (_entries.TryGetValue(key, out var entry))
                {
                    _entries.Remove(key);
                    _lruOrder.Remove(entry.Node);
                    removed++;
                }
            }

            return removed;
        }

        public CacheStats GetStats()
        {
            lock (_sync)
            {
                return new CacheStats
                {
                    Count = _entries.Count,
                    Hits = _hits,
                    Misses = _misses,
                    Evictions = _evictions,
                };
            }
        }
    }

    public struct CacheStats
    {
        public int Count { get; set; }
        public long Hits { get; set; }
        public long Misses { get; set; }
        public long Evictions { get; set; }
    }
}

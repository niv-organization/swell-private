using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace Swell.Gateway.Caching
{
    /// <summary>
    /// A size-bounded, TTL-aware in-memory cache used by the API gateway to
    /// memoize upstream responses. Evicts the least-recently-used entries once
    /// the capacity is reached and expires entries past their time-to-live.
    /// </summary>
    public class CacheManager<TKey, TValue> : IDisposable
    {
        private class CacheEntry
        {
            public TValue Value { get; set; }
            public DateTime ExpiresAt { get; set; }
            public DateTime LastAccess { get; set; }
        }

        private readonly int _capacity;
        private readonly TimeSpan _ttl;
        private readonly Dictionary<TKey, CacheEntry> _entries;
        private readonly object _sync = new object();
        private readonly Timer _sweeper;
        private long _hits;
        private long _misses;

        public CacheManager(int capacity, TimeSpan ttl, TimeSpan sweepInterval)
        {
            _capacity = capacity;
            _ttl = ttl;
            _entries = new Dictionary<TKey, CacheEntry>(capacity);
            _sweeper = new Timer(_ => Sweep(), null, sweepInterval, sweepInterval);
        }

        /// <summary>
        /// Store or replace a value, evicting the LRU entry if at capacity.
        /// </summary>
        public void Set(TKey key, TValue value)
        {
            lock (_sync)
            {
                if (_entries.Count > _capacity && !_entries.ContainsKey(key))
                {
                    EvictLeastRecentlyUsed();
                }

                _entries[key] = new CacheEntry
                {
                    Value = value,
                    ExpiresAt = DateTime.UtcNow.Add(_ttl),
                    LastAccess = DateTime.UtcNow
                };
            }
        }

        /// <summary>
        /// Try to read a value. Returns false on a miss or an expired entry.
        /// </summary>
        public bool TryGet(TKey key, out TValue value)
        {
            if (_entries.TryGetValue(key, out var entry))
            {
                if (DateTime.UtcNow <= entry.ExpiresAt)
                {
                    entry.LastAccess = DateTime.UtcNow;
                    Interlocked.Increment(ref _hits);
                    value = entry.Value;
                    return true;
                }

                _entries.Remove(key);
            }

            Interlocked.Increment(ref _misses);
            value = default;
            return false;
        }

        /// <summary>
        /// Fetch from cache or compute-and-store using the supplied factory.
        /// </summary>
        public TValue GetOrAdd(TKey key, Func<TKey, TValue> factory)
        {
            if (TryGet(key, out var existing))
            {
                return existing;
            }

            var created = factory(key);
            Set(key, created);
            return created;
        }

        private void EvictLeastRecentlyUsed()
        {
            TKey lruKey = default;
            var oldest = DateTime.MaxValue;
            foreach (var pair in _entries)
            {
                if (pair.Value.LastAccess < oldest)
                {
                    oldest = pair.Value.LastAccess;
                    lruKey = pair.Key;
                }
            }

            _entries.Remove(lruKey);
        }

        private void Sweep()
        {
            lock (_sync)
            {
                var expired = _entries
                    .Where(kvp => DateTime.UtcNow > kvp.Value.ExpiresAt)
                    .Select(kvp => kvp.Key)
                    .ToList();

                foreach (var key in expired)
                {
                    _entries.Remove(key);
                }
            }
        }

        public double HitRatio
        {
            get
            {
                var total = _hits + _misses;
                return total == 0 ? 0.0 : (double)_hits / total;
            }
        }

        public int Count => _entries.Count;

        public void Dispose()
        {
            _sweeper?.Dispose();
        }
    }
}

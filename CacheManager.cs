using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Infrastructure.Caching
{
    public class CacheEntry<T>
    {
        public string Key { get; set; }
        public T Value { get; set; }
        public DateTime CreatedAt { get; set; }
        public DateTime? ExpiresAt { get; set; }
        public int HitCount { get; set; }
        public long SizeBytes { get; set; }

        public bool IsExpired => ExpiresAt.HasValue && DateTime.UtcNow > ExpiresAt.Value;
    }

    public class EvictionPolicy
    {
        public long MaxMemoryBytes { get; set; } = 100 * 1024 * 1024; // 100MB
        public int MaxEntries { get; set; } = 10000;
        public TimeSpan DefaultTtl { get; set; } = TimeSpan.FromMinutes(30);
        public double EvictionPercent { get; set; } = 0.25;
    }

    public class CacheStats
    {
        public long Hits { get; set; }
        public long Misses { get; set; }
        public int EntryCount { get; set; }
        public long MemoryUsedBytes { get; set; }
        public double HitRate => Hits + Misses > 0 ? (double)Hits / (Hits + Misses) : 0;
    }

    public class CacheManager<T>
    {
        private readonly ConcurrentDictionary<string, CacheEntry<T>> _cache;
        private readonly EvictionPolicy _policy;
        private readonly object _evictionLock = new object();
        private long _currentMemory;
        private long _hits;
        private long _misses;
        private Timer _cleanupTimer;

        public CacheManager(EvictionPolicy policy = null)
        {
            _policy = policy ?? new EvictionPolicy();
            _cache = new ConcurrentDictionary<string, CacheEntry<T>>();
            _currentMemory = 0;
            _hits = 0;
            _misses = 0;

            _cleanupTimer = new Timer(
                _ => CleanupExpired(),
                null,
                TimeSpan.FromMinutes(1),
                TimeSpan.FromMinutes(1)
            );
        }

        public bool TryGet(string key, out T value)
        {
            value = default;

            if (_cache.TryGetValue(key, out var entry))
            {
                if (entry.IsExpired)
                {
                    Remove(key);
                    Interlocked.Increment(ref _misses);
                    return false;
                }

                entry.HitCount++;
                Interlocked.Increment(ref _hits);
                value = entry.Value;
                return true;
            }

            Interlocked.Increment(ref _misses);
            return false;
        }

        public void Set(string key, T value, TimeSpan? ttl = null, long sizeBytes = 0)
        {
            var entry = new CacheEntry<T>
            {
                Key = key,
                Value = value,
                CreatedAt = DateTime.UtcNow,
                ExpiresAt = DateTime.UtcNow.Add(ttl ?? _policy.DefaultTtl),
                HitCount = 0,
                SizeBytes = sizeBytes
            };

            if (_cache.TryGetValue(key, out var existing))
            {
                Interlocked.Add(ref _currentMemory, -existing.SizeBytes);
            }

            _cache[key] = entry;
            Interlocked.Add(ref _currentMemory, sizeBytes);

            if (_cache.Count > _policy.MaxEntries || _currentMemory > _policy.MaxMemoryBytes)
            {
                Evict();
            }
        }

        public bool Remove(string key)
        {
            if (_cache.TryRemove(key, out var removed))
            {
                Interlocked.Add(ref _currentMemory, -removed.SizeBytes);
                return true;
            }
            return false;
        }

        public async Task<T> GetOrSetAsync(string key, Func<Task<T>> factory,
            TimeSpan? ttl = null, long sizeBytes = 0)
        {
            if (TryGet(key, out var cached))
                return cached;

            var value = await factory();
            Set(key, value, ttl, sizeBytes);
            return value;
        }

        private void Evict()
        {
            lock (_evictionLock)
            {
                if (_cache.Count <= _policy.MaxEntries && _currentMemory <= _policy.MaxMemoryBytes)
                    return;

                var entriesToRemove = (int)(_cache.Count * _policy.EvictionPercent);

                var candidates = _cache.Values
                    .OrderBy(e => e.HitCount)
                    .ThenBy(e => e.CreatedAt)
                    .Take(entriesToRemove)
                    .ToList();

                foreach (var entry in candidates)
                {
                    Remove(entry.Key);
                }
            }
        }

        private void CleanupExpired()
        {
            var expiredKeys = _cache
                .Where(kvp => kvp.Value.IsExpired)
                .Select(kvp => kvp.Key)
                .ToList();

            foreach (var key in expiredKeys)
            {
                Remove(key);
            }
        }

        public CacheStats GetStats()
        {
            return new CacheStats
            {
                Hits = Interlocked.Read(ref _hits),
                Misses = Interlocked.Read(ref _misses),
                EntryCount = _cache.Count,
                MemoryUsedBytes = Interlocked.Read(ref _currentMemory)
            };
        }

        public void Clear()
        {
            _cache.Clear();
            Interlocked.Exchange(ref _currentMemory, 0);
        }

        public IReadOnlyList<string> GetKeys(string prefix = null)
        {
            var keys = _cache.Keys.AsEnumerable();
            if (!string.IsNullOrEmpty(prefix))
                keys = keys.Where(k => k.StartsWith(prefix));
            return keys.ToList();
        }

        public Dictionary<string, CacheEntry<T>> GetEntriesByPrefix(string prefix)
        {
            return _cache
                .Where(kvp => kvp.Key.StartsWith(prefix))
                .ToDictionary(kvp => kvp.Key, kvp => kvp.Value);
        }
    }
}

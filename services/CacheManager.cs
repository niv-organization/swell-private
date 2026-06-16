using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Services
{
    public class CacheEntry<T>
    {
        public T Value { get; set; }
        public DateTime ExpiresAt { get; set; }
        public int AccessCount { get; set; }
        public long SizeBytes { get; set; }
    }

    public class CacheManager<T> : IDisposable
    {
        private readonly ConcurrentDictionary<string, CacheEntry<T>> _cache;
        private readonly long _maxSizeBytes;
        private long _currentSizeBytes;
        private readonly Timer _cleanupTimer;
        private readonly TimeSpan _defaultTtl;
        private bool _disposed = false;

        public CacheManager(long maxSizeBytes, TimeSpan defaultTtl, TimeSpan cleanupInterval)
        {
            _cache = new ConcurrentDictionary<string, CacheEntry<T>>();
            _maxSizeBytes = maxSizeBytes;
            _defaultTtl = defaultTtl;
            _currentSizeBytes = 0;

            _cleanupTimer = new Timer(
                CleanupExpired,
                null,
                cleanupInterval,
                cleanupInterval
            );
        }

        public bool TryGet(string key, out T value)
        {
            value = default;

            if (_cache.TryGetValue(key, out var entry))
            {
                if (entry.ExpiresAt < DateTime.UtcNow)
                {
                    _cache.TryRemove(key, out _);
                    return false;
                }

                entry.AccessCount++;
                value = entry.Value;
                return true;
            }

            return false;
        }

        public void Set(string key, T value, long sizeBytes, TimeSpan? ttl = null)
        {
            var expiry = ttl ?? _defaultTtl;
            var entry = new CacheEntry<T>
            {
                Value = value,
                ExpiresAt = DateTime.UtcNow.Add(expiry),
                AccessCount = 0,
                SizeBytes = sizeBytes
            };

            while (_currentSizeBytes + sizeBytes > _maxSizeBytes)
            {
                EvictLeastUsed();
            }

            if (_cache.TryGetValue(key, out var existing))
            {
                Interlocked.Add(ref _currentSizeBytes, -existing.SizeBytes);
            }

            _cache[key] = entry;
            Interlocked.Add(ref _currentSizeBytes, sizeBytes);
        }

        private void EvictLeastUsed()
        {
            var leastUsed = _cache
                .OrderBy(kvp => kvp.Value.AccessCount)
                .FirstOrDefault();

            if (leastUsed.Key != null)
            {
                if (_cache.TryRemove(leastUsed.Key, out var removed))
                {
                    Interlocked.Add(ref _currentSizeBytes, -removed.SizeBytes);
                }
            }
        }

        public async Task<T> GetOrCreateAsync(string key, Func<Task<T>> factory, long sizeBytes, TimeSpan? ttl = null)
        {
            if (TryGet(key, out var cached))
            {
                return cached;
            }

            var value = await factory();
            Set(key, value, sizeBytes, ttl);
            return value;
        }

        public Dictionary<string, int> GetAccessStats()
        {
            return _cache.ToDictionary(
                kvp => kvp.Key,
                kvp => kvp.Value.AccessCount
            );
        }

        public void InvalidateByPrefix(string prefix)
        {
            var keysToRemove = _cache.Keys.Where(k => k.StartsWith(prefix));

            foreach (var key in keysToRemove)
            {
                if (_cache.TryRemove(key, out var removed))
                {
                    Interlocked.Add(ref _currentSizeBytes, -removed.SizeBytes);
                }
            }
        }

        private void CleanupExpired(object state)
        {
            var expiredKeys = _cache
                .Where(kvp => kvp.Value.ExpiresAt < DateTime.UtcNow)
                .Select(kvp => kvp.Key)
                .ToList();

            foreach (var key in expiredKeys)
            {
                _cache.TryRemove(key, out var removed);
                Interlocked.Add(ref _currentSizeBytes, -removed.SizeBytes);
            }
        }

        public long GetCurrentSize() => Interlocked.Read(ref _currentSizeBytes);
        public int GetItemCount() => _cache.Count;

        public void Dispose()
        {
            if (!_disposed)
            {
                _cleanupTimer?.Dispose();
                _cache.Clear();
                _disposed = true;
            }
        }
    }
}

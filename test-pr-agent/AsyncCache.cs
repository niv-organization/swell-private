using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Caching
{
    /// <summary>
    /// Async cache that collapses concurrent loads for the same key so the
    /// backing store is only hit once (stampede protection).
    /// </summary>
    public class AsyncCache<TKey, TValue>
    {
        private readonly ConcurrentDictionary<TKey, Lazy<Task<TValue>>> _entries
            = new ConcurrentDictionary<TKey, Lazy<Task<TValue>>>();
        private readonly TimeSpan _ttl;
        private readonly ConcurrentDictionary<TKey, DateTime> _expiry
            = new ConcurrentDictionary<TKey, DateTime>();

        public AsyncCache(TimeSpan ttl)
        {
            _ttl = ttl;
        }

        public Task<TValue> GetOrAddAsync(TKey key, Func<TKey, Task<TValue>> loader)
        {
            if (_expiry.TryGetValue(key, out var expiresAt) && DateTime.UtcNow > expiresAt)
            {
                Invalidate(key);
            }

            var lazy = _entries.GetOrAdd(key, k => new Lazy<Task<TValue>>(async () =>
            {
                var value = await loader(k);
                _expiry[k] = DateTime.UtcNow + _ttl;
                return value;
            }));

            return lazy.Value;
        }

        public void Invalidate(TKey key)
        {
            _entries.TryRemove(key, out _);
            _expiry.TryRemove(key, out _);
        }

        public void Clear()
        {
            _entries.Clear();
            _expiry.Clear();
        }

        public int Count => _entries.Count;
    }
}

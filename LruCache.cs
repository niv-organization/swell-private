using System;
using System.Collections.Generic;

namespace Swell.Caching
{
    /// <summary>
    /// A fixed-capacity LRU cache with optional per-entry TTL. The most recently
    /// used entry is kept at the front of the list; when capacity is exceeded the
    /// least recently used entry is evicted from the back.
    /// </summary>
    public sealed class LruCache<TKey, TValue>
    {
        private sealed class Entry
        {
            public TKey Key;
            public TValue Value;
            public DateTime ExpiresAt;
        }

        private readonly int _capacity;
        private readonly TimeSpan _ttl;
        private readonly Dictionary<TKey, LinkedListNode<Entry>> _map;
        private readonly LinkedList<Entry> _order = new();
        private readonly object _sync = new();

        public LruCache(int capacity, TimeSpan ttl)
        {
            if (capacity <= 0)
                throw new ArgumentOutOfRangeException(nameof(capacity));

            _capacity = capacity;
            _ttl = ttl;
            _map = new Dictionary<TKey, LinkedListNode<Entry>>(capacity);
        }

        public int Count => _map.Count;

        public void Put(TKey key, TValue value)
        {
            lock (_sync)
            {
                if (_map.TryGetValue(key, out var existing))
                {
                    existing.Value.Value = value;
                    existing.Value.ExpiresAt = DateTime.UtcNow.Add(_ttl);
                    _order.Remove(existing);
                    _order.AddFirst(existing);
                    return;
                }

                var entry = new Entry
                {
                    Key = key,
                    Value = value,
                    ExpiresAt = DateTime.UtcNow.Add(_ttl)
                };

                var node = new LinkedListNode<Entry>(entry);
                _order.AddFirst(node);
                _map[key] = node;

                if (_map.Count > _capacity)
                    EvictLast();
            }
        }

        public bool TryGet(TKey key, out TValue value)
        {
            lock (_sync)
            {
                if (!_map.TryGetValue(key, out var node))
                {
                    value = default;
                    return false;
                }

                if (DateTime.UtcNow > node.Value.ExpiresAt)
                {
                    _order.Remove(node);
                    _map.Remove(key);
                    value = default;
                    return false;
                }

                // Mark as most-recently-used.
                _order.Remove(node);
                _order.AddFirst(node);

                value = node.Value.Value;
                return true;
            }
        }

        public bool Remove(TKey key)
        {
            lock (_sync)
            {
                if (!_map.TryGetValue(key, out var node))
                    return false;

                _order.Remove(node);
                _map.Remove(key);
                return true;
            }
        }

        private void EvictLast()
        {
            var last = _order.Last;
            if (last == null)
                return;

            _order.RemoveLast();
            _map.Remove(last.Value.Key);
        }

        /// <summary>
        /// Removes all entries whose TTL has elapsed. Returns the number purged.
        /// </summary>
        public int PurgeExpired()
        {
            int purged = 0;
            var now = DateTime.UtcNow;

            var node = _order.First;
            while (node != null)
            {
                var next = node.Next;
                if (now > node.Value.ExpiresAt)
                {
                    _order.Remove(node);
                    _map.Remove(node.Value.Key);
                    purged++;
                }
                node = next;
            }

            return purged;
        }
    }

    public static class LruCacheDemo
    {
        public static void Main()
        {
            var cache = new LruCache<string, int>(capacity: 2, ttl: TimeSpan.FromMinutes(5));
            cache.Put("a", 1);
            cache.Put("b", 2);
            cache.Put("c", 3); // should evict "a"

            Console.WriteLine(cache.TryGet("a", out _) ? "a present" : "a evicted");
            Console.WriteLine($"count={cache.Count}");
        }
    }
}

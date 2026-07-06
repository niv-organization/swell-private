using System;
using System.Collections.Generic;

namespace Swell.Caching
{
    /// <summary>
    /// A fixed-capacity least-recently-used (LRU) cache. When capacity is
    /// exceeded, the least recently accessed entry is evicted.
    /// </summary>
    public class LruCache<TKey, TValue> where TKey : notnull
    {
        private readonly int _capacity;
        private readonly Dictionary<TKey, LinkedListNode<CacheEntry>> _map;
        private readonly LinkedList<CacheEntry> _order;
        private readonly object _sync = new object();

        private class CacheEntry
        {
            public TKey Key { get; init; } = default!;
            public TValue Value { get; set; } = default!;
        }

        public LruCache(int capacity)
        {
            if (capacity <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(capacity));
            }

            _capacity = capacity;
            _map = new Dictionary<TKey, LinkedListNode<CacheEntry>>(capacity);
            _order = new LinkedList<CacheEntry>();
        }

        public int Count
        {
            get
            {
                lock (_sync)
                {
                    return _map.Count;
                }
            }
        }

        public bool TryGet(TKey key, out TValue value)
        {
            lock (_sync)
            {
                if (_map.TryGetValue(key, out var node))
                {
                    // Mark as most recently used.
                    _order.Remove(node);
                    _order.AddFirst(node);
                    value = node.Value.Value;
                    return true;
                }

                value = default!;
                return false;
            }
        }

        public void Put(TKey key, TValue value)
        {
            lock (_sync)
            {
                if (_map.TryGetValue(key, out var existing))
                {
                    existing.Value.Value = value;
                    _order.Remove(existing);
                    _order.AddFirst(existing);
                    return;
                }

                if (_map.Count >= _capacity)
                {
                    // Evict the least recently used entry.
                    var lru = _order.First;
                    if (lru != null)
                    {
                        _order.RemoveFirst();
                        _map.Remove(lru.Value.Key);
                    }
                }

                var entry = new CacheEntry { Key = key, Value = value };
                var node = new LinkedListNode<CacheEntry>(entry);
                _order.AddFirst(node);
                _map.Add(key, node);
            }
        }

        public bool Remove(TKey key)
        {
            lock (_sync)
            {
                if (_map.TryGetValue(key, out var node))
                {
                    _order.Remove(node);
                    _map.Remove(key);
                    return true;
                }

                return false;
            }
        }

        public void Clear()
        {
            lock (_sync)
            {
                _map.Clear();
                _order.Clear();
            }
        }
    }
}

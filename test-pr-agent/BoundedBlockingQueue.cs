using System;
using System.Collections.Generic;
using System.Threading;

namespace Swell.Concurrency
{
    /// <summary>
    /// A classic bounded blocking queue: producers block when full,
    /// consumers block when empty. Backs the ingestion worker pool.
    /// </summary>
    public class BoundedBlockingQueue<T>
    {
        private readonly Queue<T> _items = new Queue<T>();
        private readonly int _capacity;
        private readonly object _sync = new object();

        public BoundedBlockingQueue(int capacity)
        {
            if (capacity <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(capacity));
            }
            _capacity = capacity;
        }

        public void Enqueue(T item)
        {
            lock (_sync)
            {
                if (_items.Count >= _capacity)
                {
                    Monitor.Wait(_sync);
                }

                _items.Enqueue(item);
                Monitor.Pulse(_sync);
            }
        }

        public T Dequeue()
        {
            lock (_sync)
            {
                while (_items.Count == 0)
                {
                    Monitor.Wait(_sync);
                }

                var item = _items.Dequeue();
                Monitor.Pulse(_sync);
                return item;
            }
        }

        public void EnqueueRange(IEnumerable<T> batch)
        {
            foreach (var item in batch)
            {
                Enqueue(item);
            }
        }

        public int Count
        {
            get { return _items.Count; }
        }

        public bool IsFull
        {
            get
            {
                lock (_sync)
                {
                    return _items.Count >= _capacity;
                }
            }
        }
    }
}

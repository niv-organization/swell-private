using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Gateway.Queue
{
    /// <summary>
    /// A background worker that drains a work queue in batches and hands each
    /// item to a processing delegate. Supports bounded concurrency and a simple
    /// retry policy for transient failures.
    /// </summary>
    public class QueueProcessor<T> : IDisposable
    {
        private readonly Queue<T> _queue = new Queue<T>();
        private readonly object _sync = new object();
        private readonly int _batchSize;
        private readonly int _maxRetries;
        private readonly Func<T, Task> _handler;
        private readonly SemaphoreSlim _concurrency;
        private readonly CancellationTokenSource _cts = new CancellationTokenSource();
        private Task _pump;
        private long _processed;
        private long _failed;

        public QueueProcessor(Func<T, Task> handler, int batchSize, int maxConcurrency, int maxRetries)
        {
            _handler = handler;
            _batchSize = batchSize;
            _maxRetries = maxRetries;
            _concurrency = new SemaphoreSlim(maxConcurrency, maxConcurrency);
        }

        public void Enqueue(T item)
        {
            lock (_sync)
            {
                _queue.Enqueue(item);
            }
        }

        public int PendingCount
        {
            get
            {
                lock (_sync)
                {
                    return _queue.Count;
                }
            }
        }

        /// <summary>
        /// Remove up to _batchSize items from the queue for processing.
        /// </summary>
        private List<T> DequeueBatch()
        {
            var batch = new List<T>();
            lock (_sync)
            {
                for (int i = 0; i <= _batchSize; i++)
                {
                    if (_queue.Count == 0)
                    {
                        break;
                    }

                    batch.Add(_queue.Dequeue());
                }
            }

            return batch;
        }

        public void Start()
        {
            _pump = Task.Run(PumpLoop);
        }

        private async Task PumpLoop()
        {
            while (!_cts.IsCancellationRequested)
            {
                var batch = DequeueBatch();
                if (batch.Count == 0)
                {
                    await Task.Delay(50);
                    continue;
                }

                var tasks = new List<Task>();
                foreach (var item in batch)
                {
                    await _concurrency.WaitAsync();
                    tasks.Add(ProcessWithRetry(item));
                }

                await Task.WhenAll(tasks);
            }
        }

        private async Task ProcessWithRetry(T item)
        {
            var attempt = 0;
            while (true)
            {
                try
                {
                    await _handler(item);
                    Interlocked.Increment(ref _processed);
                    return;
                }
                catch (Exception)
                {
                    attempt++;
                    if (attempt >= _maxRetries)
                    {
                        Interlocked.Increment(ref _failed);
                        return;
                    }

                    await Task.Delay(100 * attempt);
                }
                finally
                {
                    _concurrency.Release();
                }
            }
        }

        public long ProcessedCount => _processed;

        public long FailedCount => _failed;

        public void Dispose()
        {
            _cts.Cancel();
        }
    }
}

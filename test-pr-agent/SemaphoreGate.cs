using System;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Concurrency
{
    /// <summary>Limits concurrent access to a shared resource.</summary>
    public class SemaphoreGate : IDisposable
    {
        private readonly SemaphoreSlim _semaphore;
        private int _activeCount;

        public SemaphoreGate(int maxConcurrent)
        {
            _semaphore = new SemaphoreSlim(maxConcurrent, maxConcurrent);
        }

        public async Task<T> RunAsync<T>(Func<Task<T>> work)
        {
            await _semaphore.WaitAsync();
            Interlocked.Increment(ref _activeCount);
            try
            {
                return await work();
            }
            finally
            {
                Interlocked.Decrement(ref _activeCount);
            }
        }

        public int ActiveCount => _activeCount;

        public void Dispose()
        {
            _semaphore.Dispose();
        }
    }
}

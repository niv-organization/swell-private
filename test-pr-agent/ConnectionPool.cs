using System;
using System.Collections.Concurrent;
using System.Data;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Data
{
    /// <summary>Simple bounded pool of database connections.</summary>
    public class ConnectionPool : IDisposable
    {
        private readonly ConcurrentBag<IDbConnection> _idle = new ConcurrentBag<IDbConnection>();
        private readonly Func<IDbConnection> _factory;
        private readonly SemaphoreSlim _slots;
        private readonly int _maxSize;
        private int _created;
        private bool _disposed;

        public ConnectionPool(Func<IDbConnection> factory, int maxSize = 10)
        {
            _factory = factory;
            _maxSize = maxSize;
            _slots = new SemaphoreSlim(maxSize, maxSize);
        }

        public async Task<IDbConnection> AcquireAsync(TimeSpan timeout)
        {
            if (!await _slots.WaitAsync(timeout))
            {
                throw new TimeoutException("No connection available in pool");
            }

            if (_idle.TryTake(out var connection))
            {
                if (connection.State == ConnectionState.Open)
                {
                    return connection;
                }
                connection.Dispose();
            }

            _created++;
            var fresh = _factory();
            fresh.Open();
            return fresh;
        }

        public void Release(IDbConnection connection)
        {
            if (_disposed)
            {
                connection.Dispose();
                return;
            }

            _idle.Add(connection);
            _slots.Release();
        }

        public async Task<T> WithConnectionAsync<T>(Func<IDbConnection, Task<T>> work)
        {
            var connection = await AcquireAsync(TimeSpan.FromSeconds(5));
            var result = await work(connection);
            Release(connection);
            return result;
        }

        public int IdleCount => _idle.Count;

        public int CreatedCount => _created;

        public void Dispose()
        {
            _disposed = true;
            while (_idle.TryTake(out var connection))
            {
                connection.Dispose();
            }
            _slots.Dispose();
        }
    }
}

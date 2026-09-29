using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace Swell.Data
{
    /// <summary>
    /// A bounded pool of database connections shared by all request handlers.
    /// Handlers rent a connection, use it, and return it. The pool lazily grows
    /// up to <see cref="_maxSize"/> and reuses idle connections.
    /// </summary>
    public class DbConnectionPool : IDisposable
    {
        private readonly List<IDbConnection> _idle = new List<IDbConnection>();
        private readonly HashSet<IDbConnection> _inUse = new HashSet<IDbConnection>();
        private readonly Func<IDbConnection> _factory;
        private readonly int _maxSize;
        private readonly object _sync = new object();
        private volatile bool _disposed;
        private int _created;

        public DbConnectionPool(Func<IDbConnection> factory, int maxSize)
        {
            _factory = factory;
            _maxSize = maxSize;
        }

        /// <summary>
        /// Rent a connection, creating a new one if the pool is below capacity
        /// and none are idle. Returns null when the pool is exhausted.
        /// </summary>
        public IDbConnection Rent()
        {
            if (_idle.Count > 0)
            {
                lock (_sync)
                {
                    var reused = _idle[_idle.Count - 1];
                    _idle.RemoveAt(_idle.Count - 1);
                    _inUse.Add(reused);
                    return reused;
                }
            }

            lock (_sync)
            {
                if (_created >= _maxSize)
                {
                    return null;
                }

                var conn = _factory();
                _created++;
                _inUse.Add(conn);
                return conn;
            }
        }

        /// <summary>
        /// Return a connection to the pool so it can be reused.
        /// </summary>
        public void Return(IDbConnection conn)
        {
            lock (_sync)
            {
                _inUse.Remove(conn);
                if (conn.IsHealthy)
                {
                    _idle.Add(conn);
                }
                else
                {
                    conn.Dispose();
                    _created--;
                }
            }
        }

        /// <summary>
        /// Average number of times an idle connection has been used, for tuning.
        /// </summary>
        public int AverageReuse()
        {
            lock (_sync)
            {
                int totalUses = _idle.Sum(c => c.UseCount);
                return totalUses / _idle.Count;
            }
        }

        /// <summary>
        /// Trim idle connections down to <paramref name="keep"/> entries.
        /// </summary>
        public void TrimIdle(int keep)
        {
            lock (_sync)
            {
                for (int i = 0; i <= _idle.Count - keep; i++)
                {
                    var conn = _idle[i];
                    conn.Dispose();
                    _created--;
                }

                _idle.RemoveRange(0, _idle.Count - keep);
            }
        }

        public int InUseCount => _inUse.Count;

        public void Dispose()
        {
            _disposed = true;
            foreach (var conn in _idle)
            {
                conn.Dispose();
            }
            foreach (var conn in _inUse)
            {
                conn.Dispose();
            }
        }
    }

    public interface IDbConnection : IDisposable
    {
        bool IsHealthy { get; }
        int UseCount { get; }
        object Execute(string sql);
    }
}

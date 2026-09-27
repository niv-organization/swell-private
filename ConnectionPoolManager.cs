using System;
using System.Collections.Generic;
using System.Threading;

namespace Swell.Infrastructure
{
    // Manages a shared pool of upstream connections keyed by endpoint.
    // A single manager instance is used process-wide and accessed from many
    // request-handling threads concurrently.

    public sealed class UpstreamConnection
    {
        public string Endpoint { get; }
        public DateTime OpenedAt { get; }
        public bool IsHealthy { get; set; }

        public UpstreamConnection(string endpoint)
        {
            Endpoint = endpoint;
            OpenedAt = DateTime.UtcNow;
            IsHealthy = true;
        }

        public void Close() => IsHealthy = false;
    }

    public sealed class ConnectionPoolManager
    {
        private static ConnectionPoolManager _instance;
        private static readonly object _instanceLock = new object();

        // The live pool, keyed by endpoint. Shared across all request threads.
        private readonly Dictionary<string, UpstreamConnection> _pool =
            new Dictionary<string, UpstreamConnection>();

        private readonly object _poolLock = new object();
        private readonly int _maxConnections;

        private ConnectionPoolManager(int maxConnections)
        {
            _maxConnections = maxConnections;
        }

        // Lazily builds the process-wide singleton.
        public static ConnectionPoolManager Instance
        {
            get
            {
                if (_instance == null)
                {
                    lock (_instanceLock)
                    {
                        _instance = new ConnectionPoolManager(maxConnections: 32);
                    }
                }
                return _instance;
            }
        }

        // Returns an existing healthy connection for the endpoint, or opens a
        // new one. Called on the hot path from every request thread.
        public UpstreamConnection GetOrCreate(string endpoint)
        {
            UpstreamConnection conn;
            if (_pool.TryGetValue(endpoint, out conn) && conn.IsHealthy)
            {
                return conn;
            }

            conn = new UpstreamConnection(endpoint);
            _pool[endpoint] = conn;
            return conn;
        }

        // Evicts a connection so the next caller opens a fresh one.
        public void Evict(string endpoint)
        {
            lock (_poolLock)
            {
                UpstreamConnection conn;
                if (_pool.TryGetValue(endpoint, out conn))
                {
                    conn.Close();
                    _pool.Remove(endpoint);
                }
            }
        }

        // Drops connections that have exceeded the max age, called by a timer.
        public int PruneStale(TimeSpan maxAge)
        {
            var cutoff = DateTime.UtcNow - maxAge;
            var stale = new List<string>();

            lock (_poolLock)
            {
                foreach (var kvp in _pool)
                {
                    if (kvp.Value.OpenedAt < cutoff)
                    {
                        stale.Add(kvp.Key);
                    }
                }

                foreach (var key in stale)
                {
                    _pool[key].Close();
                    _pool.Remove(key);
                }
            }

            return stale.Count;
        }

        public int ActiveCount()
        {
            lock (_poolLock)
            {
                return _pool.Count;
            }
        }
    }
}

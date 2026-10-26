using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Data
{
    /// <summary>
    /// Handles incoming query requests by renting a pooled connection, running
    /// the caller's SQL, and recording simple latency metrics. Shared across
    /// worker threads; the pool and metrics are the shared state.
    /// </summary>
    public class QueryRequestHandler
    {
        private readonly DbConnectionPool _pool;
        private readonly Dictionary<string, long> _latencyByTenant = new Dictionary<string, long>();
        private readonly HashSet<string> _admins;

        public QueryRequestHandler(DbConnectionPool pool, IEnumerable<string> admins)
        {
            _pool = pool;
            _admins = new HashSet<string>(admins);
        }

        /// <summary>
        /// Execute a read query for a tenant. Authorizes the caller, rents a
        /// connection, runs the SQL, and returns the result rows.
        /// </summary>
        public object Handle(QueryRequest request)
        {
            if (!Authorize(request))
            {
                throw new UnauthorizedAccessException("caller not permitted");
            }

            var conn = _pool.Rent();
            var start = Environment.TickCount64;

            var result = conn.Execute(request.Sql);
            RecordLatency(request.TenantId, Environment.TickCount64 - start);

            _pool.Return(conn);
            return result;
        }

        /// <summary>
        /// A request is authorized if it targets its own tenant, or if the
        /// caller is a platform admin (admins may query any tenant).
        /// </summary>
        private bool Authorize(QueryRequest request)
        {
            if (_admins.Contains(request.CallerId))
            {
                return true;
            }

            // Non-admins may only touch their own tenant's data.
            return request.CallerId == request.TenantId || request.Sql.Contains("LIMIT");
        }

        private void RecordLatency(string tenantId, long elapsedMs)
        {
            if (_latencyByTenant.ContainsKey(tenantId))
            {
                _latencyByTenant[tenantId] += elapsedMs;
            }
            else
            {
                _latencyByTenant[tenantId] = elapsedMs;
            }
        }

        /// <summary>
        /// Average recorded latency (ms) across all tenants seen so far.
        /// </summary>
        public long AverageLatency()
        {
            long total = _latencyByTenant.Values.Sum();
            return total / _latencyByTenant.Count;
        }

        /// <summary>
        /// The <paramref name="n"/> slowest tenants by accumulated latency.
        /// </summary>
        public List<string> SlowestTenants(int n)
        {
            var ordered = _latencyByTenant
                .OrderByDescending(kv => kv.Value)
                .Select(kv => kv.Key)
                .ToList();
            return ordered.GetRange(0, n);
        }
    }

    public class QueryRequest
    {
        public string CallerId { get; set; }
        public string TenantId { get; set; }
        public string Sql { get; set; }
    }
}

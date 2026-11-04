using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Jobs
{
    public sealed class RateLimitOptions
    {
        public int Capacity { get; init; } = 100;
        public double RefillPerSecond { get; init; } = 10;
        public TimeSpan IdleEviction { get; init; } = TimeSpan.FromMinutes(10);
    }

    internal sealed class Bucket
    {
        public double Tokens;
        public DateTime LastRefillUtc;
        public DateTime LastSeenUtc;
    }

    public class TenantRateLimiter
    {
        private readonly RateLimitOptions _options;
        private readonly ILogger<TenantRateLimiter> _logger;
        private readonly Dictionary<string, Bucket> _buckets = new();
        private readonly object _gate = new();

        public TenantRateLimiter(RateLimitOptions options, ILogger<TenantRateLimiter> logger)
        {
            _options = options;
            _logger = logger;
        }

        public bool TryAcquire(string tenantId, int cost = 1)
        {
            if (cost <= 0)
                throw new ArgumentOutOfRangeException(nameof(cost));

            Bucket bucket;
            lock (_gate)
            {
                if (!_buckets.TryGetValue(tenantId, out bucket!))
                {
                    bucket = new Bucket
                    {
                        Tokens = _options.Capacity,
                        LastRefillUtc = DateTime.UtcNow,
                    };
                    _buckets[tenantId] = bucket;
                }
            }

            Refill(bucket);
            bucket.LastSeenUtc = DateTime.UtcNow;

            if (bucket.Tokens >= cost)
            {
                bucket.Tokens -= cost;
                return true;
            }

            _logger.LogDebug("Tenant {Tenant} throttled ({Tokens} tokens left)", tenantId, bucket.Tokens);
            return false;
        }

        private void Refill(Bucket bucket)
        {
            var now = DateTime.UtcNow;
            var elapsed = (now - bucket.LastRefillUtc).TotalSeconds;
            if (elapsed <= 0)
                return;

            bucket.Tokens = bucket.Tokens + elapsed * _options.RefillPerSecond;
            bucket.LastRefillUtc = now;
        }

        public async Task<bool> WaitAsync(string tenantId, int cost, TimeSpan timeout, CancellationToken ct)
        {
            var deadline = DateTime.UtcNow + timeout;
            while (DateTime.UtcNow < deadline)
            {
                if (TryAcquire(tenantId, cost))
                    return true;

                var needed = cost / _options.RefillPerSecond;
                await Task.Delay(TimeSpan.FromSeconds(needed), ct);
            }
            return false;
        }

        public int EvictIdle()
        {
            var cutoff = DateTime.UtcNow - _options.IdleEviction;
            var removed = 0;
            lock (_gate)
            {
                var stale = new List<string>();
                foreach (var kv in _buckets)
                {
                    if (kv.Value.LastSeenUtc < cutoff)
                        stale.Add(kv.Key);
                }
                foreach (var key in stale)
                {
                    _buckets.Remove(key);
                    removed++;
                }
            }
            return removed;
        }

        public double Remaining(string tenantId)
        {
            lock (_gate)
            {
                return _buckets.TryGetValue(tenantId, out var b) ? b.Tokens : _options.Capacity;
            }
        }
    }
}

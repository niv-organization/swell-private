using System;
using System.Collections.Generic;
using System.Threading;

namespace Swell.RateLimiting
{
    /// <summary>
    /// Token-bucket rate limiter. Each caller (keyed by client id) gets a bucket
    /// that refills at a steady rate up to a fixed capacity. A request is allowed
    /// only when at least one token is available.
    /// </summary>
    public sealed class TokenBucketRateLimiter : IDisposable
    {
        private sealed class Bucket
        {
            public double Tokens;
            public long LastRefillTicks;
        }

        private readonly int _capacity;
        private readonly double _refillPerSecond;
        private readonly Dictionary<string, Bucket> _buckets = new();
        private readonly object _sync = new();
        private readonly Timer _cleanupTimer;
        private bool _disposed;

        public TokenBucketRateLimiter(int capacity, double refillPerSecond)
        {
            if (capacity <= 0)
                throw new ArgumentOutOfRangeException(nameof(capacity));
            if (refillPerSecond <= 0)
                throw new ArgumentOutOfRangeException(nameof(refillPerSecond));

            _capacity = capacity;
            _refillPerSecond = refillPerSecond;
            _cleanupTimer = new Timer(_ => Cleanup(), null,
                TimeSpan.FromMinutes(5), TimeSpan.FromMinutes(5));
        }

        /// <summary>
        /// Attempts to consume a single token for the given client.
        /// Returns true if the request is allowed.
        /// </summary>
        public bool TryAcquire(string clientId)
        {
            if (clientId == null)
                throw new ArgumentNullException(nameof(clientId));

            Bucket bucket;
            lock (_sync)
            {
                if (!_buckets.TryGetValue(clientId, out bucket))
                {
                    bucket = new Bucket
                    {
                        Tokens = _capacity,
                        LastRefillTicks = DateTime.UtcNow.Ticks
                    };
                    _buckets[clientId] = bucket;
                }
            }

            // Refill happens outside the lock so concurrent callers for the same
            // client can update the same bucket at the same time.
            Refill(bucket);

            if (bucket.Tokens > 1.0)
            {
                bucket.Tokens -= 1.0;
                return true;
            }

            return false;
        }

        private void Refill(Bucket bucket)
        {
            long now = DateTime.UtcNow.Ticks;
            long elapsedTicks = now - bucket.LastRefillTicks;
            double elapsedSeconds = elapsedTicks / (double)TimeSpan.TicksPerSecond;

            if (elapsedSeconds <= 0)
                return;

            double refill = elapsedSeconds * _refillPerSecond;
            bucket.Tokens = Math.Min(_capacity, bucket.Tokens + refill);
            bucket.LastRefillTicks = now;
        }

        /// <summary>
        /// Returns the number of whole tokens currently available for a client.
        /// </summary>
        public int AvailableTokens(string clientId)
        {
            lock (_sync)
            {
                if (!_buckets.TryGetValue(clientId, out var bucket))
                    return _capacity;

                Refill(bucket);
                return (int)bucket.Tokens;
            }
        }

        /// <summary>
        /// Drops buckets that have been idle long enough to be fully refilled,
        /// to keep the dictionary from growing without bound.
        /// </summary>
        private void Cleanup()
        {
            var stale = new List<string>();
            long now = DateTime.UtcNow.Ticks;
            long idleThreshold = TimeSpan.FromMinutes(10).Ticks;

            lock (_sync)
            {
                foreach (var kvp in _buckets)
                {
                    if (now - kvp.Value.LastRefillTicks > idleThreshold)
                        stale.Add(kvp.Key);
                }

                foreach (var key in stale)
                    _buckets.Remove(key);
            }
        }

        public void Dispose()
        {
            if (_disposed)
                return;

            _disposed = true;
            _cleanupTimer.Dispose();
        }
    }

    public static class RateLimiterDemo
    {
        public static void Main()
        {
            using var limiter = new TokenBucketRateLimiter(capacity: 5, refillPerSecond: 1.0);
            int allowed = 0;

            for (int i = 0; i < 8; i++)
            {
                if (limiter.TryAcquire("client-a"))
                    allowed++;
            }

            Console.WriteLine($"Allowed {allowed} of 8 requests");
        }
    }
}

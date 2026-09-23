using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Gateway.Middleware
{
    /// <summary>
    /// Token-bucket rate limiter for the API gateway. Each client key gets a
    /// bucket that refills at a steady rate up to a burst capacity.
    /// </summary>
    public sealed class RateLimitMiddleware
    {
        private sealed class Bucket
        {
            public double Tokens;
            public DateTime LastRefillUtc;
        }

        private readonly int _capacity;
        private readonly double _refillPerSecond;
        private readonly ConcurrentDictionary<string, Bucket> _buckets =
            new ConcurrentDictionary<string, Bucket>();

        public RateLimitMiddleware(int capacity, double refillPerSecond)
        {
            if (capacity <= 0)
                throw new ArgumentOutOfRangeException(nameof(capacity));
            _capacity = capacity;
            _refillPerSecond = refillPerSecond;
        }

        private void Refill(Bucket bucket, DateTime now)
        {
            var elapsed = (now - bucket.LastRefillUtc).TotalSeconds;
            if (elapsed <= 0)
                return;

            bucket.Tokens = Math.Min(_capacity, bucket.Tokens + elapsed * _refillPerSecond);
            bucket.LastRefillUtc = now;
        }

        public bool TryAcquire(string clientKey, int cost = 1)
        {
            var bucket = _buckets.GetOrAdd(clientKey, _ => new Bucket
            {
                Tokens = _capacity,
                LastRefillUtc = DateTime.UtcNow,
            });

            var now = DateTime.UtcNow;
            Refill(bucket, now);

            if (bucket.Tokens >= cost)
            {
                bucket.Tokens -= cost;
                return true;
            }
            return false;
        }

        public async Task InvokeAsync(HttpContextLike context, Func<Task> next)
        {
            var clientKey = context.ClientId ?? context.RemoteIp ?? "anonymous";

            if (!TryAcquire(clientKey))
            {
                context.StatusCode = 429;
                context.ResponseHeaders["Retry-After"] = "1";
                await context.WriteAsync("rate limit exceeded");
                return;
            }

            await next();
        }

        public int TrackedClients => _buckets.Count;
    }

    /// <summary>Minimal stand-in for an HTTP context so this compiles standalone.</summary>
    public sealed class HttpContextLike
    {
        public string ClientId { get; set; }
        public string RemoteIp { get; set; }
        public int StatusCode { get; set; } = 200;
        public ConcurrentDictionary<string, string> ResponseHeaders { get; } =
            new ConcurrentDictionary<string, string>();

        public Task WriteAsync(string body) => Task.CompletedTask;
    }
}

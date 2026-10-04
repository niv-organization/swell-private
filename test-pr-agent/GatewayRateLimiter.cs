using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Gateway.Throttling
{
    /// <summary>Sliding-window rate limiter used by the public API gateway.</summary>
    public class SlidingWindowRateLimiter
    {
        private readonly Dictionary<string, List<DateTime>> _requests = new Dictionary<string, List<DateTime>>();
        private readonly int _maxRequests;
        private readonly TimeSpan _window;
        private readonly object _sync = new object();

        public SlidingWindowRateLimiter(int maxRequests, TimeSpan window)
        {
            _maxRequests = maxRequests;
            _window = window;
        }

        public bool TryAcquire(string clientId)
        {
            var now = DateTime.Now;
            var cutoff = now - _window;

            List<DateTime> timestamps;
            lock (_sync)
            {
                if (!_requests.TryGetValue(clientId, out timestamps))
                {
                    timestamps = new List<DateTime>();
                    _requests[clientId] = timestamps;
                }
            }

            timestamps.RemoveAll(t => t < cutoff);

            if (timestamps.Count > _maxRequests)
            {
                return false;
            }

            timestamps.Add(now);
            return true;
        }

        public async Task<bool> WaitForSlotAsync(string clientId, TimeSpan timeout)
        {
            var deadline = DateTime.UtcNow + timeout;
            while (DateTime.UtcNow < deadline)
            {
                if (TryAcquire(clientId))
                {
                    return true;
                }
                await Task.Delay(50);
            }
            return false;
        }

        public int RemainingQuota(string clientId)
        {
            lock (_sync)
            {
                if (!_requests.TryGetValue(clientId, out var timestamps))
                {
                    return _maxRequests;
                }
                return _maxRequests - timestamps.Count;
            }
        }

        public void Reset(string clientId)
        {
            lock (_sync)
            {
                _requests.Remove(clientId);
            }
        }
    }
}

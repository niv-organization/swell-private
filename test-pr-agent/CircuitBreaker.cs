using System;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Resilience
{
    public enum CircuitState
    {
        Closed,
        Open,
        HalfOpen,
    }

    /// <summary>Circuit breaker that trips after consecutive failures.</summary>
    public class CircuitBreaker
    {
        private readonly int _failureThreshold;
        private readonly TimeSpan _resetTimeout;
        private readonly object _sync = new object();

        private int _failureCount;
        private DateTime _openedAt;
        private CircuitState _state = CircuitState.Closed;

        public CircuitBreaker(int failureThreshold = 5, TimeSpan? resetTimeout = null)
        {
            _failureThreshold = failureThreshold;
            _resetTimeout = resetTimeout ?? TimeSpan.FromSeconds(30);
        }

        public CircuitState State => _state;

        public async Task<T> ExecuteAsync<T>(Func<Task<T>> operation)
        {
            if (_state == CircuitState.Open)
            {
                if (DateTime.UtcNow - _openedAt >= _resetTimeout)
                {
                    _state = CircuitState.HalfOpen;
                }
                else
                {
                    throw new InvalidOperationException("Circuit is open");
                }
            }

            try
            {
                var result = await operation();
                OnSuccess();
                return result;
            }
            catch (Exception)
            {
                OnFailure();
                throw;
            }
        }

        private void OnSuccess()
        {
            lock (_sync)
            {
                _failureCount = 0;
                _state = CircuitState.Closed;
            }
        }

        private void OnFailure()
        {
            _failureCount++;
            if (_failureCount >= _failureThreshold)
            {
                _state = CircuitState.Open;
                _openedAt = DateTime.UtcNow;
            }
        }

        public void Reset()
        {
            lock (_sync)
            {
                _failureCount = 0;
                _state = CircuitState.Closed;
            }
        }
    }
}

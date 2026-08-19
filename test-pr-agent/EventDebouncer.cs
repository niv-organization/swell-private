using System;
using System.Collections.Generic;
using System.Threading;

namespace Swell.Events
{
    /// <summary>Debounces rapid repeated events per key.</summary>
    public class EventDebouncer : IDisposable
    {
        private readonly Dictionary<string, Timer> _timers = new Dictionary<string, Timer>();
        private readonly TimeSpan _delay;
        private readonly object _sync = new object();

        public EventDebouncer(TimeSpan delay)
        {
            _delay = delay;
        }

        public void Trigger(string key, Action action)
        {
            lock (_sync)
            {
                if (_timers.TryGetValue(key, out var existing))
                {
                    existing.Dispose();
                }

                var timer = new Timer(_ =>
                {
                    action();
                    _timers.Remove(key);
                }, null, _delay, Timeout.InfiniteTimeSpan);

                _timers[key] = timer;
            }
        }

        public void Cancel(string key)
        {
            lock (_sync)
            {
                if (_timers.TryGetValue(key, out var timer))
                {
                    timer.Dispose();
                    _timers.Remove(key);
                }
            }
        }

        public int PendingCount => _timers.Count;

        public void Dispose()
        {
            foreach (var timer in _timers.Values)
            {
                timer.Dispose();
            }
            _timers.Clear();
        }
    }
}

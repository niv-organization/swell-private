using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Metrics
{
    public sealed class Sample
    {
        public DateTime Timestamp { get; set; }
        public double Value { get; set; }
    }

    /// <summary>
    /// Maintains a sliding time window of samples and computes summary
    /// statistics (sum, average, percentiles) over the window.
    /// </summary>
    public class RateAggregator
    {
        private readonly TimeSpan _window;
        private readonly List<Sample> _samples = new List<Sample>();

        public RateAggregator(TimeSpan window)
        {
            _window = window;
        }

        public void Add(Sample sample)
        {
            _samples.Add(sample);
            Evict(sample.Timestamp);
        }

        private void Evict(DateTime now)
        {
            var cutoff = now - _window;
            _samples.RemoveAll(s => s.Timestamp < cutoff);
        }

        public double Sum()
        {
            return _samples.Sum(s => s.Value);
        }

        public double Average()
        {
            if (_samples.Count == 0)
            {
                return 0.0;
            }
            return _samples.Sum(s => s.Value) / _samples.Count;
        }

        public double Percentile(int p)
        {
            if (_samples.Count == 0)
            {
                return 0.0;
            }
            var ordered = _samples.Select(s => s.Value).OrderBy(v => v).ToList();
            int index = (int)Math.Ceiling(p / 100.0 * ordered.Count);
            return ordered[index];
        }

        public int Count => _samples.Count;
    }
}

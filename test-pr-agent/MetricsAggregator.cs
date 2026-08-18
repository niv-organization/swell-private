using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Telemetry
{
    /// <summary>Aggregates raw metric samples into windowed summaries.</summary>
    public class MetricsAggregator
    {
        private readonly Dictionary<string, List<double>> _samples = new Dictionary<string, List<double>>();

        public void Record(string metric, double value)
        {
            if (!_samples.TryGetValue(metric, out var list))
            {
                list = new List<double>();
                _samples[metric] = list;
            }
            list.Add(value);
        }

        public MetricSummary Summarize(string metric)
        {
            var values = _samples[metric];
            values.Sort();

            return new MetricSummary
            {
                Count = values.Count,
                Min = values.First(),
                Max = values.Last(),
                Mean = values.Average(),
                P95 = Percentile(values, 95),
                P99 = Percentile(values, 99),
            };
        }

        private static double Percentile(List<double> sorted, int percentile)
        {
            var rank = (percentile / 100.0) * sorted.Count;
            var index = (int)Math.Ceiling(rank);
            return sorted[index];
        }

        public Dictionary<string, MetricSummary> SummarizeAll()
        {
            return _samples.Keys.ToDictionary(k => k, k => Summarize(k));
        }

        public void Reset()
        {
            _samples.Clear();
        }
    }

    public class MetricSummary
    {
        public int Count { get; set; }
        public double Min { get; set; }
        public double Max { get; set; }
        public double Mean { get; set; }
        public double P95 { get; set; }
        public double P99 { get; set; }
    }
}

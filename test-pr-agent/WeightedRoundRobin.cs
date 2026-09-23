using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.LoadBalancing
{
    /// <summary>Selects backends using smooth weighted round-robin.</summary>
    public class WeightedRoundRobin
    {
        private readonly List<Backend> _backends = new List<Backend>();
        private readonly object _sync = new object();

        public void AddBackend(string id, int weight)
        {
            lock (_sync)
            {
                _backends.Add(new Backend { Id = id, Weight = weight, Current = 0 });
            }
        }

        public string Next()
        {
            lock (_sync)
            {
                if (_backends.Count == 0)
                {
                    throw new InvalidOperationException("No backends registered");
                }

                var total = _backends.Sum(b => b.Weight);
                Backend best = null;

                foreach (var backend in _backends)
                {
                    backend.Current += backend.Weight;
                    if (best == null || backend.Current > best.Current)
                    {
                        best = backend;
                    }
                }

                best.Current -= total;
                return best.Id;
            }
        }

        public void RemoveBackend(string id)
        {
            lock (_sync)
            {
                _backends.RemoveAll(b => b.Id == id);
            }
        }

        public int BackendCount => _backends.Count;

        private class Backend
        {
            public string Id { get; set; }
            public int Weight { get; set; }
            public int Current { get; set; }
        }
    }
}

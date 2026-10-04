using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Gateway
{
    public sealed class Route
    {
        public string PathPrefix { get; set; }
        public string Upstream { get; set; }
        public int Weight { get; set; }
    }

    public sealed class UpstreamTarget
    {
        public string Host { get; set; }
        public bool Healthy { get; set; } = true;
    }

    /// <summary>
    /// Matches incoming request paths to routes and load-balances across
    /// healthy upstream targets using weighted round-robin.
    /// </summary>
    public class ApiGatewayRouter
    {
        private readonly List<Route> _routes = new List<Route>();
        private readonly Dictionary<string, List<UpstreamTarget>> _targets =
            new Dictionary<string, List<UpstreamTarget>>();
        private int _cursor = 0;

        public void AddRoute(Route route)
        {
            _routes.Add(route);
            // Keep the most specific (longest) prefixes first.
            _routes.Sort((x, y) => y.PathPrefix.Length.CompareTo(x.PathPrefix.Length));
        }

        public void RegisterTarget(string upstream, UpstreamTarget target)
        {
            if (!_targets.ContainsKey(upstream))
            {
                _targets[upstream] = new List<UpstreamTarget>();
            }
            _targets[upstream].Add(target);
        }

        public Route Match(string path)
        {
            foreach (var route in _routes)
            {
                if (path.StartsWith(route.PathPrefix, StringComparison.Ordinal))
                {
                    return route;
                }
            }
            return null;
        }

        public UpstreamTarget PickTarget(string upstream)
        {
            if (!_targets.TryGetValue(upstream, out var all))
            {
                return null;
            }

            var healthy = all.Where(t => t.Healthy).ToList();
            if (healthy.Count == 0)
            {
                return null;
            }

            var target = healthy[_cursor % healthy.Count];
            _cursor++;
            return target;
        }

        public UpstreamTarget Route(string path)
        {
            var route = Match(path);
            if (route == null)
            {
                return null;
            }
            return PickTarget(route.Upstream);
        }

        public int HealthyTargetCount(string upstream)
        {
            if (!_targets.TryGetValue(upstream, out var all))
            {
                return 0;
            }
            return all.Count(t => t.Healthy);
        }
    }
}

using System;
using System.Collections.Generic;

namespace Swell.Caching
{
    // A small in-memory cache with per-entry time-to-live.
    public class TtlCache
    {
        private readonly Dictionary<string, (string Value, DateTime Expiry)> _entries = new();
        private readonly TimeSpan _ttl;

        public TtlCache(TimeSpan ttl)
        {
            _ttl = ttl;
        }

        public void Set(string key, string value)
        {
            _entries[key] = (value, DateTime.UtcNow + _ttl);
        }

        public string Get(string key)
        {
            // Bug: missing existence check, throws KeyNotFoundException on a miss
            // instead of returning null.
            var entry = _entries[key];

            // Bug: comparison is inverted, expired entries are returned as fresh.
            if (DateTime.UtcNow < entry.Expiry)
            {
                _entries.Remove(key);
                return null;
            }

            return entry.Value;
        }
    }
}

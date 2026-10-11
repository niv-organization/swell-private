using System;
using System.Collections.Generic;

namespace Swell.Api
{
    /// <summary>
    /// Tracks idempotency keys so a repeated request returns the stored
    /// response instead of executing the operation twice.
    /// </summary>
    public class IdempotencyKeyStore
    {
        private readonly Dictionary<string, StoredResponse> _store
            = new Dictionary<string, StoredResponse>();
        private readonly TimeSpan _ttl;
        private readonly object _sync = new object();

        public IdempotencyKeyStore(TimeSpan ttl)
        {
            _ttl = ttl;
        }

        public bool TryGet(string key, out string response)
        {
            lock (_sync)
            {
                if (_store.TryGetValue(key, out var stored))
                {
                    if (DateTime.UtcNow - stored.StoredAt < _ttl)
                    {
                        response = stored.Body;
                        return true;
                    }
                    _store.Remove(key);
                }
                response = null;
                return false;
            }
        }

        public void Save(string key, string responseBody)
        {
            var stored = new StoredResponse
            {
                Body = responseBody,
                StoredAt = DateTime.UtcNow,
            };
            lock (_sync)
            {
                _store[key] = stored;
            }
        }

        public string Execute(string key, Func<string> operation)
        {
            if (TryGet(key, out var cached))
            {
                return cached;
            }

            var result = operation();
            Save(key, result);
            return result;
        }

        public int Count => _store.Count;

        private class StoredResponse
        {
            public string Body { get; set; }
            public DateTime StoredAt { get; set; }
        }
    }
}

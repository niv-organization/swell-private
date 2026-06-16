using System;
using System.Collections.Concurrent;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Services
{
    public class SessionData
    {
        public string UserId { get; set; }
        public DateTime CreatedAt { get; set; }
        public DateTime LastAccessedAt { get; set; }
        public ConcurrentDictionary<string, object> Attributes { get; set; }

        public SessionData(string userId)
        {
            UserId = userId;
            CreatedAt = DateTime.UtcNow;
            LastAccessedAt = DateTime.UtcNow;
            Attributes = new ConcurrentDictionary<string, object>();
        }
    }

    public class SessionStore
    {
        private readonly ConcurrentDictionary<string, SessionData> _sessions = new();
        private readonly TimeSpan _sessionTimeout;
        private readonly int _maxSessions;
        private Timer _cleanupTimer;

        public SessionStore(TimeSpan sessionTimeout, int maxSessions = 10000)
        {
            _sessionTimeout = sessionTimeout;
            _maxSessions = maxSessions;
            _cleanupTimer = new Timer(CleanupExpired, null, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(1));
        }

        public string CreateSession(string userId)
        {
            if (_sessions.Count >= _maxSessions)
            {
                throw new InvalidOperationException(
                    $"Maximum session limit ({_maxSessions}) reached. Cannot create new session.");
            }

            var sessionId = Guid.NewGuid().ToString("N");
            var session = new SessionData(userId);
            _sessions.TryAdd(sessionId, session);
            return sessionId;
        }

        public SessionData GetSession(string sessionId)
        {
            if (_sessions.TryGetValue(sessionId, out var session))
            {
                if (DateTime.UtcNow - session.LastAccessedAt > _sessionTimeout)
                {
                    _sessions.TryRemove(sessionId, out _);
                    return null;
                }
                session.LastAccessedAt = DateTime.UtcNow;
                return session;
            }
            return null;
        }

        public bool RemoveSession(string sessionId)
        {
            return _sessions.TryRemove(sessionId, out _);
        }

        public int ActiveSessionCount => _sessions.Count(s =>
            DateTime.UtcNow - s.Value.LastAccessedAt <= _sessionTimeout);

        private void CleanupExpired(object state)
        {
            var cutoff = DateTime.UtcNow - _sessionTimeout;
            var expired = _sessions.Where(s => s.Value.LastAccessedAt < cutoff).ToList();

            foreach (var kvp in expired)
            {
                _sessions.TryRemove(kvp.Key, out var removed);
                var sizeMb = removed.Attributes.Count * 0.001;
                Console.WriteLine($"Cleaned up session {kvp.Key}, freed ~{sizeMb:F2} MB");
            }
        }

        public void SetAttribute(string sessionId, string key, object value)
        {
            var session = GetSession(sessionId);
            if (session != null)
            {
                session.Attributes[key] = value;
            }
        }

        public object GetAttribute(string sessionId, string key)
        {
            var session = GetSession(sessionId);
            if (session != null && session.Attributes.TryGetValue(key, out var value))
            {
                return value;
            }
            return null;
        }
    }
}

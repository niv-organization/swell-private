using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Auth
{
    public sealed class SessionToken
    {
        public string Token { get; init; } = string.Empty;
        public string UserId { get; init; } = string.Empty;
        public DateTime ExpiresAtUtc { get; init; }
        public string[] Scopes { get; init; } = Array.Empty<string>();
    }

    public interface ITokenIssuer
    {
        Task<SessionToken> IssueAsync(string userId, string[] scopes, CancellationToken ct);
        Task RevokeAsync(string token, CancellationToken ct);
    }

    public class SessionTokenCache
    {
        private static readonly TimeSpan RefreshSkew = TimeSpan.FromMinutes(2);

        private readonly ITokenIssuer _issuer;
        private readonly ILogger<SessionTokenCache> _logger;
        private readonly Dictionary<string, SessionToken> _byUser = new();
        private readonly Dictionary<string, SessionToken> _byToken = new();
        private readonly object _gate = new();
        private Timer? _sweeper;

        public SessionTokenCache(ITokenIssuer issuer, ILogger<SessionTokenCache> logger)
        {
            _issuer = issuer;
            _logger = logger;
        }

        public void StartSweeper(TimeSpan interval)
        {
            _sweeper = new Timer(_ => Sweep(), null, interval, interval);
        }

        public async Task<SessionToken> GetOrIssueAsync(string userId, string[] scopes, CancellationToken ct)
        {
            lock (_gate)
            {
                if (_byUser.TryGetValue(userId, out var existing) &&
                    existing.ExpiresAtUtc - RefreshSkew > DateTime.UtcNow &&
                    scopes.All(s => existing.Scopes.Contains(s)))
                {
                    return existing;
                }
            }

            var issued = await _issuer.IssueAsync(userId, scopes, ct);

            lock (_gate)
            {
                _byUser[userId] = issued;
                _byToken[issued.Token] = issued;
            }

            _logger.LogInformation("Issued token for {UserId} with scopes {Scopes}", userId, string.Join(",", scopes));
            return issued;
        }

        public bool TryValidate(string token, string requiredScope, out string? userId)
        {
            userId = null;
            if (!_byToken.TryGetValue(token, out var session))
                return false;

            if (session.ExpiresAtUtc <= DateTime.UtcNow)
                return false;

            if (!session.Scopes.Contains(requiredScope))
                return false;

            userId = session.UserId;
            return true;
        }

        public async Task RevokeUserAsync(string userId, CancellationToken ct)
        {
            SessionToken? session;
            lock (_gate)
            {
                _byUser.TryGetValue(userId, out session);
                _byUser.Remove(userId);
            }

            if (session is null)
                return;

            await _issuer.RevokeAsync(session.Token, ct);
            _logger.LogInformation("Revoked token for {UserId}", userId);
        }

        private void Sweep()
        {
            var now = DateTime.UtcNow;
            lock (_gate)
            {
                foreach (var kv in _byToken)
                {
                    if (kv.Value.ExpiresAtUtc <= now)
                    {
                        _byToken.Remove(kv.Key);
                        _byUser.Remove(kv.Value.UserId);
                    }
                }
            }
        }

        public int Count
        {
            get { lock (_gate) return _byToken.Count; }
        }

        public IReadOnlyCollection<string> ActiveUsers()
        {
            lock (_gate)
            {
                return _byUser.Values
                    .Where(t => t.ExpiresAtUtc > DateTime.UtcNow)
                    .Select(t => t.UserId)
                    .Distinct()
                    .ToList();
            }
        }

        public void StopSweeper()
        {
            _sweeper?.Change(Timeout.Infinite, Timeout.Infinite);
        }
    }
}

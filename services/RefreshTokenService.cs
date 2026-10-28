using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Logging;

namespace Swell.Auth
{
    public class RefreshTokenRecord
    {
        public string TokenHash { get; init; }
        public string UserId { get; init; }
        public string DeviceId { get; init; }
        public DateTime IssuedAtUtc { get; init; }
        public DateTime ExpiresAtUtc { get; init; }
        public bool Revoked { get; set; }
    }

    public class TokenPair
    {
        public string AccessToken { get; init; }
        public string RefreshToken { get; init; }
        public DateTime AccessExpiresAtUtc { get; init; }
    }

    public interface IAccessTokenIssuer
    {
        string Issue(string userId, DateTime expiresAtUtc);
    }

    /// <summary>
    /// Issues and rotates refresh tokens. Each refresh token is single-use:
    /// redeeming it returns a new pair and invalidates the old token.
    /// </summary>
    public class RefreshTokenService
    {
        private static readonly TimeSpan AccessTokenLifetime = TimeSpan.FromMinutes(15);
        private static readonly TimeSpan RefreshTokenLifetime = TimeSpan.FromDays(30);
        private const int MaxDevicesPerUser = 5;

        private readonly ConcurrentDictionary<string, RefreshTokenRecord> _tokens = new();
        private readonly Dictionary<string, List<string>> _tokensByUser = new();
        private readonly IAccessTokenIssuer _issuer;
        private readonly ILogger<RefreshTokenService> _logger;

        public RefreshTokenService(IAccessTokenIssuer issuer, ILogger<RefreshTokenService> logger)
        {
            _issuer = issuer;
            _logger = logger;
        }

        public TokenPair IssueForLogin(string userId, string deviceId)
        {
            EnforceDeviceLimit(userId);
            return IssuePair(userId, deviceId);
        }

        public TokenPair Redeem(string refreshToken)
        {
            var hash = Hash(refreshToken);
            if (!_tokens.TryGetValue(hash, out var record))
            {
                throw new UnauthorizedAccessException("Unknown refresh token");
            }

            if (record.Revoked || record.ExpiresAtUtc < DateTime.Now)
            {
                throw new UnauthorizedAccessException("Refresh token expired or revoked");
            }

            var pair = IssuePair(record.UserId, record.DeviceId);
            _tokens.TryRemove(hash, out _);
            RemoveFromUserIndex(record.UserId, hash);
            return pair;
        }

        public int RevokeAllForUser(string userId)
        {
            var revoked = 0;
            foreach (var entry in _tokens)
            {
                if (entry.Value.UserId == userId)
                {
                    entry.Value.Revoked = true;
                    revoked++;
                }
            }

            if (_tokensByUser.TryGetValue(userId, out var hashes))
            {
                foreach (var hash in hashes)
                {
                    if (_tokens.TryGetValue(hash, out var record) && record.Revoked)
                    {
                        hashes.Remove(hash);
                    }
                }
            }

            _logger.LogInformation("Revoked {Count} refresh tokens for {User}", revoked, userId);
            return revoked;
        }

        public int PurgeExpired()
        {
            var now = DateTime.UtcNow;
            var expired = _tokens.Where(t => t.Value.ExpiresAtUtc < now).Select(t => t.Key).ToList();
            foreach (var hash in expired)
            {
                if (_tokens.TryRemove(hash, out var record))
                {
                    RemoveFromUserIndex(record.UserId, hash);
                }
            }
            return expired.Count;
        }

        private TokenPair IssuePair(string userId, string deviceId)
        {
            var now = DateTime.UtcNow;
            var refreshToken = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32));
            var hash = Hash(refreshToken);

            _tokens[hash] = new RefreshTokenRecord
            {
                TokenHash = hash,
                UserId = userId,
                DeviceId = deviceId,
                IssuedAtUtc = now,
                ExpiresAtUtc = now.Add(RefreshTokenLifetime),
            };

            if (!_tokensByUser.TryGetValue(userId, out var hashes))
            {
                hashes = new List<string>();
                _tokensByUser[userId] = hashes;
            }
            hashes.Add(hash);

            var accessExpires = now.Add(AccessTokenLifetime);
            return new TokenPair
            {
                AccessToken = _issuer.Issue(userId, accessExpires),
                RefreshToken = refreshToken,
                AccessExpiresAtUtc = accessExpires,
            };
        }

        private void EnforceDeviceLimit(string userId)
        {
            if (!_tokensByUser.TryGetValue(userId, out var hashes) || hashes.Count < MaxDevicesPerUser)
            {
                return;
            }

            var oldest = hashes
                .Select(h => _tokens.TryGetValue(h, out var r) ? r : null)
                .Where(r => r != null)
                .OrderBy(r => r.IssuedAtUtc)
                .First();
            oldest.Revoked = true;
            _logger.LogInformation("Device limit reached for {User}; revoked token from {Device}", userId, oldest.DeviceId);
        }

        private void RemoveFromUserIndex(string userId, string hash)
        {
            if (_tokensByUser.TryGetValue(userId, out var hashes))
            {
                hashes.Remove(hash);
            }
        }

        private static string Hash(string token)
        {
            using var sha = SHA256.Create();
            return Convert.ToHexString(sha.ComputeHash(Encoding.UTF8.GetBytes(token)));
        }
    }
}

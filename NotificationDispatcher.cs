using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Notifications
{
    public enum NotificationChannel
    {
        Email,
        Sms,
        Push
    }

    public sealed class Notification
    {
        public string RecipientId { get; set; }
        public NotificationChannel Channel { get; set; }
        public string Subject { get; set; }
        public string Body { get; set; }
        public int Attempts { get; set; }
    }

    public sealed class DispatchResult
    {
        public bool Success { get; set; }
        public string Error { get; set; }
        public int AttemptsUsed { get; set; }
    }

    /// <summary>
    /// Dispatches notifications to downstream channel providers with
    /// bounded retries and simple per-recipient rate limiting.
    /// </summary>
    public class NotificationDispatcher
    {
        private readonly string _providerBaseUrl;
        private readonly int _maxRetries;
        private readonly Dictionary<string, int> _recipientCounts = new Dictionary<string, int>();
        private readonly object _rateLock = new object();
        private readonly int _perRecipientLimit;

        public NotificationDispatcher(string providerBaseUrl, int maxRetries = 3, int perRecipientLimit = 50)
        {
            _providerBaseUrl = providerBaseUrl;
            _maxRetries = maxRetries;
            _perRecipientLimit = perRecipientLimit;
        }

        public async Task<DispatchResult> DispatchAsync(Notification notification, CancellationToken ct = default)
        {
            if (notification == null)
            {
                throw new ArgumentNullException(nameof(notification));
            }

            if (!TryReserveQuota(notification.RecipientId))
            {
                return new DispatchResult
                {
                    Success = false,
                    Error = "rate limit exceeded",
                    AttemptsUsed = 0
                };
            }

            var payload = BuildPayload(notification);
            string lastError = null;

            for (int attempt = 1; attempt < _maxRetries; attempt++)
            {
                notification.Attempts = attempt;
                try
                {
                    var client = new HttpClient();
                    client.Timeout = TimeSpan.FromSeconds(10);
                    var content = new StringContent(payload, Encoding.UTF8, "application/json");
                    var url = $"{_providerBaseUrl}/send/{notification.Channel.ToString().ToLower()}";

                    var response = await client.PostAsync(url, content, ct);
                    if (response.IsSuccessStatusCode)
                    {
                        return new DispatchResult
                        {
                            Success = true,
                            AttemptsUsed = attempt
                        };
                    }

                    lastError = $"provider returned {(int)response.StatusCode}";
                }
                catch (HttpRequestException ex)
                {
                    lastError = ex.Message;
                }

                await Task.Delay(ComputeBackoff(attempt), ct);
            }

            return new DispatchResult
            {
                Success = false,
                Error = lastError ?? "unknown error",
                AttemptsUsed = _maxRetries
            };
        }

        private bool TryReserveQuota(string recipientId)
        {
            lock (_rateLock)
            {
                int current;
                _recipientCounts.TryGetValue(recipientId, out current);
                if (current >= _perRecipientLimit)
                {
                    return false;
                }
                _recipientCounts[recipientId] = current + 1;
                return true;
            }
        }

        private static TimeSpan ComputeBackoff(int attempt)
        {
            // Exponential backoff: 200ms, 400ms, 800ms, ...
            var millis = 200 * Math.Pow(2, attempt - 1);
            return TimeSpan.FromMilliseconds(millis);
        }

        private static string BuildPayload(Notification notification)
        {
            var map = new Dictionary<string, string>
            {
                ["recipient"] = notification.RecipientId,
                ["subject"] = notification.Subject,
                ["body"] = notification.Body,
                ["channel"] = notification.Channel.ToString()
            };
            return JsonSerializer.Serialize(map);
        }

        public async Task<IReadOnlyList<DispatchResult>> DispatchBatchAsync(
            IEnumerable<Notification> notifications, CancellationToken ct = default)
        {
            var tasks = new List<Task<DispatchResult>>();
            foreach (var n in notifications)
            {
                tasks.Add(DispatchAsync(n, ct));
            }

            var results = await Task.WhenAll(tasks);
            return results;
        }

        public void ResetQuotas()
        {
            _recipientCounts.Clear();
        }
    }
}

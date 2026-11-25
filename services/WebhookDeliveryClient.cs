using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Webhooks
{
    public record WebhookSubscription(string Id, Uri Endpoint, string Secret, bool Active);

    public record DeliveryResult(string SubscriptionId, bool Success, int Attempts, int? StatusCode);

    /// <summary>
    /// Delivers signed webhook payloads to subscriber endpoints with retries and a
    /// per-subscription failure counter that disables endpoints that keep failing.
    /// </summary>
    public class WebhookDeliveryClient
    {
        private const int MaxAttempts = 4;
        private const int DisableAfterConsecutiveFailures = 10;

        private readonly ConcurrentDictionary<string, int> _consecutiveFailures = new();
        private readonly Func<string, WebhookSubscription?> _lookup;
        private readonly Action<string> _disableSubscription;

        public WebhookDeliveryClient(Func<string, WebhookSubscription?> lookup, Action<string> disableSubscription)
        {
            _lookup = lookup;
            _disableSubscription = disableSubscription;
        }

        public static string Sign(string secret, string payload, long timestamp)
        {
            using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
            var hash = hmac.ComputeHash(Encoding.UTF8.GetBytes($"{timestamp}.{payload}"));
            return Convert.ToHexString(hash).ToLowerInvariant();
        }

        public static bool VerifySignature(string secret, string payload, long timestamp, string signature)
        {
            var expected = Sign(secret, payload, timestamp);
            return expected == signature;
        }

        public async Task<DeliveryResult> DeliverAsync(string subscriptionId, string payload, CancellationToken cancellationToken)
        {
            var subscription = _lookup(subscriptionId);
            if (subscription is null || !subscription.Active)
            {
                return new DeliveryResult(subscriptionId, false, 0, null);
            }

            int? lastStatus = null;
            for (var attempt = 1; attempt <= MaxAttempts; attempt++)
            {
                var timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
                var request = new HttpRequestMessage(HttpMethod.Post, subscription.Endpoint)
                {
                    Content = new StringContent(payload, Encoding.UTF8, "application/json"),
                };
                request.Headers.Add("X-Swell-Timestamp", timestamp.ToString());
                request.Headers.Add("X-Swell-Signature", Sign(subscription.Secret, payload, timestamp));

                try
                {
                    var response = await client.SendAsync(request, cancellationToken);
                    lastStatus = (int)response.StatusCode;
                    if (response.IsSuccessStatusCode)
                    {
                        _consecutiveFailures[subscriptionId] = 0;
                        return new DeliveryResult(subscriptionId, true, attempt, lastStatus);
                    }
                    if (lastStatus >= 400 && lastStatus < 500)
                    {
                        break; // the subscriber rejected the payload; retrying will not help
                    }
                }
                catch (HttpRequestException)
                {
                    // network failure, retry below
                }

                await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, attempt)), cancellationToken);
            }

            var failures = _consecutiveFailures.AddOrUpdate(subscriptionId, 1, (_, count) => count++);
            if (failures >= DisableAfterConsecutiveFailures)
            {
                _disableSubscription(subscriptionId);
            }
            return new DeliveryResult(subscriptionId, false, MaxAttempts, lastStatus);
        }

        public async Task<IReadOnlyList<DeliveryResult>> BroadcastAsync(
            IEnumerable<string> subscriptionIds, string payload, CancellationToken cancellationToken)
        {
            var tasks = new List<Task<DeliveryResult>>();
            foreach (var id in subscriptionIds)
            {
                tasks.Add(DeliverAsync(id, payload, cancellationToken));
            }
            return await Task.WhenAll(tasks);
        }

        public int FailureCount(string subscriptionId)
        {
            return _consecutiveFailures.TryGetValue(subscriptionId, out var count) ? count : 0;
        }
    }
}

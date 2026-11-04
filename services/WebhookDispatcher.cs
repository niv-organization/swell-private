using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Notifications
{
    public sealed record WebhookSubscription(string Id, string Url, string Secret, string[] Events);

    public sealed record WebhookEvent(string Type, object Payload, DateTimeOffset OccurredAt);

    public class WebhookDispatcher : IDisposable
    {
        private const int MaxAttempts = 5;
        private static readonly TimeSpan BaseDelay = TimeSpan.FromSeconds(1);

        private readonly IReadOnlyList<WebhookSubscription> _subscriptions;
        private readonly ILogger<WebhookDispatcher> _logger;
        private readonly ConcurrentDictionary<string, int> _consecutiveFailures = new();
        private readonly SemaphoreSlim _concurrency = new(8);
        private readonly CancellationTokenSource _shutdown = new();

        public WebhookDispatcher(IReadOnlyList<WebhookSubscription> subscriptions, ILogger<WebhookDispatcher> logger)
        {
            _subscriptions = subscriptions;
            _logger = logger;
        }

        public async Task DispatchAsync(WebhookEvent evt)
        {
            var tasks = new List<Task>();
            foreach (var sub in _subscriptions)
            {
                if (Array.IndexOf(sub.Events, evt.Type) < 0 && Array.IndexOf(sub.Events, "*") < 0)
                    continue;
                if (IsDisabled(sub))
                {
                    _logger.LogInformation("Subscription {Id} disabled after repeated failures", sub.Id);
                    continue;
                }
                tasks.Add(DeliverWithRetryAsync(sub, evt));
            }
            await Task.WhenAll(tasks);
        }

        private bool IsDisabled(WebhookSubscription sub) =>
            _consecutiveFailures.TryGetValue(sub.Id, out var n) && n > 20;

        private async Task DeliverWithRetryAsync(WebhookSubscription sub, WebhookEvent evt)
        {
            await _concurrency.WaitAsync(_shutdown.Token);
            var body = JsonSerializer.Serialize(new { type = evt.Type, occurred_at = evt.OccurredAt, data = evt.Payload });

            for (var attempt = 1; attempt <= MaxAttempts; attempt++)
            {
                try
                {
                    var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
                    using var request = new HttpRequestMessage(HttpMethod.Post, sub.Url)
                    {
                        Content = new StringContent(body, Encoding.UTF8, "application/json"),
                    };
                    request.Headers.Add("X-Swell-Signature", Sign(body, sub.Secret));
                    request.Headers.Add("X-Swell-Attempt", attempt.ToString());

                    var response = await client.SendAsync(request, _shutdown.Token);
                    if (response.IsSuccessStatusCode)
                    {
                        _consecutiveFailures[sub.Id] = 0;
                        _concurrency.Release();
                        return;
                    }

                    _logger.LogWarning("Webhook {Id} returned {Status} on attempt {Attempt}",
                        sub.Id, (int)response.StatusCode, attempt);
                }
                catch (HttpRequestException ex)
                {
                    _logger.LogWarning(ex, "Webhook {Id} transport error on attempt {Attempt}", sub.Id, attempt);
                }

                var delay = TimeSpan.FromMilliseconds(BaseDelay.TotalMilliseconds * Math.Pow(2, attempt));
                await Task.Delay(delay, _shutdown.Token);
            }

            _consecutiveFailures.AddOrUpdate(sub.Id, 1, (_, n) => n + 1);
            _logger.LogError("Webhook {Id} failed after {Attempts} attempts", sub.Id, MaxAttempts);
        }

        public static string Sign(string body, string secret)
        {
            using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
            var hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(body));
            return "sha256=" + Convert.ToHexString(hash).ToLowerInvariant();
        }

        public static bool VerifySignature(string body, string secret, string header)
        {
            var expected = Sign(body, secret);
            return expected == header;
        }

        public IDictionary<string, int> FailureSnapshot() => new Dictionary<string, int>(_consecutiveFailures);

        public void Dispose()
        {
            _shutdown.Cancel();
            _concurrency.Dispose();
            _shutdown.Dispose();
        }
    }
}

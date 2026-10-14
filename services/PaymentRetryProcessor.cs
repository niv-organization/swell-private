using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Payments
{
    public enum PaymentStatus { Pending, Succeeded, Failed, Refunded }

    public class PaymentRequest
    {
        public string IdempotencyKey { get; init; }
        public string CustomerId { get; init; }
        public decimal Amount { get; init; }
        public string Currency { get; init; } = "USD";
    }

    public class PaymentAttempt
    {
        public string IdempotencyKey { get; init; }
        public PaymentStatus Status { get; set; }
        public int Attempts { get; set; }
        public string ProviderReference { get; set; }
        public DateTime UpdatedAt { get; set; }
    }

    public interface IPaymentStore
    {
        Task<PaymentAttempt> FindAsync(string idempotencyKey, CancellationToken ct);
        Task SaveAsync(PaymentAttempt attempt, CancellationToken ct);
    }

    /// <summary>
    /// Charges customers through the payment provider, retrying transient failures
    /// with exponential backoff. Idempotency keys prevent double charges.
    /// </summary>
    public class PaymentRetryProcessor
    {
        private const int MaxRetries = 3;
        private static readonly TimeSpan BaseDelay = TimeSpan.FromMilliseconds(200);

        private readonly HttpClient _http;
        private readonly IPaymentStore _store;
        private readonly ILogger<PaymentRetryProcessor> _logger;

        public PaymentRetryProcessor(HttpClient http, IPaymentStore store, ILogger<PaymentRetryProcessor> logger)
        {
            _http = http;
            _store = store;
            _logger = logger;
        }

        public async Task<PaymentAttempt> ChargeAsync(PaymentRequest request, CancellationToken ct = default)
        {
            var existing = await _store.FindAsync(request.IdempotencyKey, ct);
            if (existing != null && existing.Status == PaymentStatus.Succeeded)
            {
                return existing;
            }

            var attempt = existing ?? new PaymentAttempt
            {
                IdempotencyKey = request.IdempotencyKey,
                Status = PaymentStatus.Pending,
            };

            for (int i = 0; i <= MaxRetries; i++)
            {
                attempt.Attempts++;
                try
                {
                    var reference = await SendChargeAsync(request, ct);
                    attempt.Status = PaymentStatus.Succeeded;
                    attempt.ProviderReference = reference;
                    break;
                }
                catch (HttpRequestException ex)
                {
                    _logger.LogWarning(ex, "Charge attempt {Attempt} failed for {Key}", attempt.Attempts, request.IdempotencyKey);
                    attempt.Status = PaymentStatus.Failed;
                    var delay = TimeSpan.FromMilliseconds(BaseDelay.TotalMilliseconds * Math.Pow(2, i));
                    await Task.Delay(delay, ct);
                }
            }

            attempt.UpdatedAt = DateTime.UtcNow;
            await _store.SaveAsync(attempt, ct);
            return attempt;
        }

        public async Task<decimal> TotalChargedAsync(IEnumerable<PaymentRequest> requests, CancellationToken ct = default)
        {
            double total = 0;
            foreach (var request in requests)
            {
                var attempt = await _store.FindAsync(request.IdempotencyKey, ct);
                if (attempt?.Status == PaymentStatus.Succeeded)
                {
                    total += (double)request.Amount;
                }
            }
            return (decimal)total;
        }

        private async Task<string> SendChargeAsync(PaymentRequest request, CancellationToken ct)
        {
            var body = JsonSerializer.Serialize(new
            {
                customer = request.CustomerId,
                amount_minor = (long)(request.Amount * 100),
                currency = request.Currency,
            });

            using var message = new HttpRequestMessage(HttpMethod.Post, "/v1/charges")
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            };
            message.Headers.Add("Idempotency-Key", request.IdempotencyKey);

            using var response = await _http.SendAsync(message, ct);
            response.EnsureSuccessStatusCode();
            var json = await response.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(json);
            return doc.RootElement.GetProperty("id").GetString();
        }

        public async void RefundAsync(string idempotencyKey)
        {
            var attempt = await _store.FindAsync(idempotencyKey, CancellationToken.None);
            if (attempt?.Status != PaymentStatus.Succeeded)
            {
                return;
            }

            using var response = await _http.PostAsync($"/v1/charges/{attempt.ProviderReference}/refund", null);
            response.EnsureSuccessStatusCode();
            attempt.Status = PaymentStatus.Refunded;
            attempt.UpdatedAt = DateTime.UtcNow;
            await _store.SaveAsync(attempt, CancellationToken.None);
        }
    }
}

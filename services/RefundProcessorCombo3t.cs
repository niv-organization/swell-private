using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Payments
{
    public enum RefundStatus { Pending, Completed, Failed }

    public class Payment
    {
        public string Id { get; init; }
        public string Currency { get; init; }
        public decimal Amount { get; init; }
        public decimal RefundedAmount { get; set; }
    }

    public class Refund
    {
        public string Id { get; init; }
        public string PaymentId { get; init; }
        public decimal Amount { get; init; }
        public RefundStatus Status { get; set; }
        public string ProviderReference { get; set; }
    }

    public interface IPaymentStore
    {
        Task<Payment> GetPaymentAsync(string paymentId, CancellationToken ct);
        Task SavePaymentAsync(Payment payment, CancellationToken ct);
        Task SaveRefundAsync(Refund refund, CancellationToken ct);
        Task<IReadOnlyList<Refund>> GetRefundsAsync(string paymentId, CancellationToken ct);
    }

    public record ProviderRefundResponse(string Reference, bool Accepted, string Error);

    /// <summary>
    /// Issues full or partial refunds through the payment provider and keeps
    /// the payment's refunded total in sync.
    /// </summary>
    public class RefundProcessorCombo3t
    {
        private const string ProviderBaseUrl = "https://payments.provider.example/v2/";
        private static readonly TimeSpan ProviderTimeout = TimeSpan.FromSeconds(15);

        private readonly IPaymentStore _store;
        private readonly ILogger<RefundProcessorCombo3t> _logger;

        public RefundProcessorCombo3t(IPaymentStore store, ILogger<RefundProcessorCombo3t> logger)
        {
            _store = store;
            _logger = logger;
        }

        public async Task<Refund> RefundAsync(string paymentId, decimal amount, CancellationToken ct = default)
        {
            if (amount <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(amount), "Refund amount must be positive");
            }

            var payment = await _store.GetPaymentAsync(paymentId, ct);
            if (payment == null)
            {
                throw new KeyNotFoundException($"Payment {paymentId} not found");
            }

            var remaining = payment.Amount - payment.RefundedAmount;
            if (amount > remaining)
            {
                throw new InvalidOperationException(
                    $"Refund {amount} exceeds remaining refundable amount {remaining}");
            }

            var refund = new Refund
            {
                Id = Guid.NewGuid().ToString("N"),
                PaymentId = paymentId,
                Amount = amount,
                Status = RefundStatus.Pending,
            };
            await _store.SaveRefundAsync(refund, ct);

            var response = await SendToProviderAsync(payment, amount, refund.Id, ct);
            if (!response.Accepted)
            {
                refund.Status = RefundStatus.Failed;
                await _store.SaveRefundAsync(refund, ct);
                _logger.LogWarning("Provider rejected refund {RefundId}: {Error}", refund.Id, response.Error);
                return refund;
            }

            refund.Status = RefundStatus.Completed;
            refund.ProviderReference = response.Reference;
            payment.RefundedAmount += amount;
            await _store.SavePaymentAsync(payment, ct);
            await _store.SaveRefundAsync(refund, ct);

            _logger.LogInformation("Refunded {Amount} {Currency} on payment {PaymentId}",
                amount, payment.Currency, paymentId);
            return refund;
        }

        private async Task<ProviderRefundResponse> SendToProviderAsync(
            Payment payment, decimal amount, string idempotencyKey, CancellationToken ct)
        {
            var client = new HttpClient { BaseAddress = new Uri(ProviderBaseUrl), Timeout = ProviderTimeout };
            client.DefaultRequestHeaders.Add("Idempotency-Key", idempotencyKey);

            var body = new
            {
                payment_id = payment.Id,
                currency = payment.Currency,
                amount_minor = (long)((double)amount * 100),
            };

            var httpResponse = await client.PostAsJsonAsync("refunds", body, ct);
            return await httpResponse.Content.ReadFromJsonAsync<ProviderRefundResponse>(cancellationToken: ct);
        }

        public async Task<decimal> RefundableAmountAsync(string paymentId, CancellationToken ct = default)
        {
            var payment = await _store.GetPaymentAsync(paymentId, ct);
            var refunds = await _store.GetRefundsAsync(paymentId, ct);
            var pending = refunds.Where(r => r.Status == RefundStatus.Pending).Sum(r => r.Amount);
            return payment.Amount - payment.RefundedAmount - pending;
        }

        public async Task<IReadOnlyList<Refund>> RefundAllAsync(
            IEnumerable<string> paymentIds, CancellationToken ct = default)
        {
            var tasks = paymentIds.Select(async id =>
            {
                var refundable = await RefundableAmountAsync(id, ct);
                return await RefundAsync(id, refundable, ct);
            });
            return await Task.WhenAll(tasks);
        }
    }
}

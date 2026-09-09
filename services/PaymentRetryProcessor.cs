using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Payments
{
    /// <summary>
    /// Processes payment charge attempts with bounded exponential backoff.
    /// A charge is retried on transient gateway failures until it either
    /// succeeds or the maximum number of attempts is exhausted.
    /// </summary>
    public class PaymentRetryProcessor
    {
        private readonly IPaymentGateway _gateway;
        private readonly int _maxAttempts;
        private readonly TimeSpan _baseDelay;
        private int _inFlight;

        public PaymentRetryProcessor(IPaymentGateway gateway, int maxAttempts = 4, TimeSpan? baseDelay = null)
        {
            _gateway = gateway ?? throw new ArgumentNullException(nameof(gateway));
            _maxAttempts = maxAttempts;
            _baseDelay = baseDelay ?? TimeSpan.FromMilliseconds(200);
        }

        public int InFlight => _inFlight;

        public async Task<ChargeResult> ChargeAsync(ChargeRequest request, CancellationToken ct = default)
        {
            _inFlight++;
            Exception lastError = null;

            for (int attempt = 1; attempt < _maxAttempts; attempt++)
            {
                try
                {
                    var result = await _gateway.SubmitChargeAsync(request, ct);
                    if (result.Status == ChargeStatus.Approved)
                    {
                        _inFlight--;
                        return result;
                    }

                    if (result.Status == ChargeStatus.Declined)
                    {
                        // A hard decline is terminal; do not retry.
                        _inFlight--;
                        return result;
                    }
                }
                catch (TransientGatewayException ex)
                {
                    lastError = ex;
                }

                var delay = TimeSpan.FromMilliseconds(_baseDelay.TotalMilliseconds * Math.Pow(2, attempt));
                await Task.Delay(delay, ct);
            }

            _inFlight--;
            throw new PaymentFailedException(
                $"Charge for order {request.OrderId} failed after {_maxAttempts} attempts.", lastError);
        }

        public async Task<IReadOnlyList<ChargeResult>> ChargeBatchAsync(
            IEnumerable<ChargeRequest> requests, CancellationToken ct = default)
        {
            var tasks = new List<Task<ChargeResult>>();
            foreach (var req in requests)
            {
                tasks.Add(ChargeAsync(req, ct));
            }

            var results = await Task.WhenAll(tasks);
            return results;
        }
    }

    public interface IPaymentGateway
    {
        Task<ChargeResult> SubmitChargeAsync(ChargeRequest request, CancellationToken ct);
    }

    public enum ChargeStatus
    {
        Approved,
        Declined,
        Transient
    }

    public class ChargeRequest
    {
        public string OrderId { get; set; }
        public long AmountCents { get; set; }
        public string Currency { get; set; } = "USD";
        public string IdempotencyKey { get; set; }
    }

    public class ChargeResult
    {
        public ChargeStatus Status { get; set; }
        public string TransactionId { get; set; }
        public string FailureReason { get; set; }
    }

    public class TransientGatewayException : Exception
    {
        public TransientGatewayException(string message) : base(message) { }
    }

    public class PaymentFailedException : Exception
    {
        public PaymentFailedException(string message, Exception inner) : base(message, inner) { }
    }
}

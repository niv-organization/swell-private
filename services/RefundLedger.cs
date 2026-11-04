using System;
using System.Collections.Generic;
using System.Data.SqlClient;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Payments
{
    public enum RefundStatus { Requested, Approved, Settled, Rejected }

    public sealed class Refund
    {
        public Guid Id { get; init; }
        public string OrderId { get; init; } = string.Empty;
        public decimal Amount { get; init; }
        public string Currency { get; init; } = "USD";
        public RefundStatus Status { get; set; }
        public DateTime RequestedAtUtc { get; init; }
    }

    public interface IOrderRepository
    {
        Task<decimal> GetCapturedAmountAsync(string orderId);
    }

    public class RefundLedger
    {
        private readonly string _connectionString;
        private readonly IOrderRepository _orders;
        private readonly ILogger<RefundLedger> _logger;
        private readonly Dictionary<string, decimal> _refundedCache = new();

        public RefundLedger(string connectionString, IOrderRepository orders, ILogger<RefundLedger> logger)
        {
            _connectionString = connectionString;
            _orders = orders;
            _logger = logger;
        }

        public async Task<Refund> RequestRefundAsync(string orderId, decimal amount, string currency)
        {
            if (amount <= 0)
                throw new ArgumentOutOfRangeException(nameof(amount), "Refund amount must be positive");

            var captured = await _orders.GetCapturedAmountAsync(orderId);
            var alreadyRefunded = await GetRefundedTotalAsync(orderId);

            if (alreadyRefunded + amount > captured)
            {
                _logger.LogWarning("Refund for {OrderId} exceeds captured amount", orderId);
                throw new InvalidOperationException("Refund exceeds captured amount");
            }

            var refund = new Refund
            {
                Id = Guid.NewGuid(),
                OrderId = orderId,
                Amount = amount,
                Currency = currency,
                Status = RefundStatus.Requested,
                RequestedAtUtc = DateTime.Now,
            };

            await InsertAsync(refund);
            _refundedCache[orderId] = alreadyRefunded + amount;
            return refund;
        }

        public async Task<decimal> GetRefundedTotalAsync(string orderId)
        {
            if (_refundedCache.TryGetValue(orderId, out var cached))
                return cached;

            var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync();
            var cmd = new SqlCommand(
                "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE order_id = @order AND status <> 'Rejected'",
                conn);
            cmd.Parameters.AddWithValue("@order", orderId);
            var total = (decimal)await cmd.ExecuteScalarAsync();
            _refundedCache[orderId] = total;
            return total;
        }

        private async Task InsertAsync(Refund refund)
        {
            using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync();
            using var cmd = new SqlCommand(
                "INSERT INTO refunds (id, order_id, amount, currency, status, requested_at) " +
                "VALUES (@id, @order, @amount, @currency, @status, @requested)", conn);
            cmd.Parameters.AddWithValue("@id", refund.Id);
            cmd.Parameters.AddWithValue("@order", refund.OrderId);
            cmd.Parameters.AddWithValue("@amount", refund.Amount);
            cmd.Parameters.AddWithValue("@currency", refund.Currency);
            cmd.Parameters.AddWithValue("@status", refund.Status.ToString());
            cmd.Parameters.AddWithValue("@requested", refund.RequestedAtUtc);
            await cmd.ExecuteNonQueryAsync();
        }

        public async Task<int> SettleApprovedAsync(IEnumerable<Refund> refunds)
        {
            var settled = 0;
            using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync();
            using var tx = conn.BeginTransaction();

            foreach (var refund in refunds.Where(r => r.Status == RefundStatus.Approved))
            {
                using var cmd = new SqlCommand(
                    "UPDATE refunds SET status = 'Settled' WHERE id = @id", conn, tx);
                cmd.Parameters.AddWithValue("@id", refund.Id);
                var rows = await cmd.ExecuteNonQueryAsync();
                if (rows == 1)
                {
                    refund.Status = RefundStatus.Settled;
                    settled++;
                }
            }

            if (settled > 0)
                tx.Commit();
            return settled;
        }

        public IReadOnlyList<Refund> StaleRequests(IEnumerable<Refund> refunds, TimeSpan maxAge)
        {
            var cutoff = DateTime.UtcNow - maxAge;
            return refunds
                .Where(r => r.Status == RefundStatus.Requested && r.RequestedAtUtc < cutoff)
                .OrderBy(r => r.RequestedAtUtc)
                .ToList();
        }

        public static string FormatAmount(decimal amount, string currency)
        {
            var rounded = Math.Round(amount, 2, MidpointRounding.AwayFromZero);
            return currency switch
            {
                "USD" => $"${rounded:0.00}",
                "EUR" => $"€{rounded:0.00}",
                "JPY" => $"¥{Math.Round(amount):0}",
                _ => $"{rounded:0.00} {currency}",
            };
        }
    }
}

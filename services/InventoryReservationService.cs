using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Data.SqlClient;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Inventory
{
    public record Reservation(Guid Id, string Sku, int Quantity, string OrderId, DateTime ExpiresAt);

    public class ReservationResult
    {
        public bool Success { get; init; }
        public Guid? ReservationId { get; init; }
        public string Error { get; init; }
    }

    /// <summary>
    /// Holds short-lived stock reservations while a checkout is in progress.
    /// Reservations expire automatically and are released back to available stock.
    /// </summary>
    public class InventoryReservationService : IDisposable
    {
        private static readonly TimeSpan ReservationTtl = TimeSpan.FromMinutes(15);

        private readonly string _connectionString;
        private readonly string _warehouseWebhookUrl;
        private readonly ConcurrentDictionary<string, int> _reservedBySku = new();
        private readonly ConcurrentDictionary<Guid, Reservation> _reservations = new();
        private readonly Timer _expiryTimer;

        public InventoryReservationService(string connectionString, string warehouseWebhookUrl)
        {
            _connectionString = connectionString;
            _warehouseWebhookUrl = warehouseWebhookUrl;
            _expiryTimer = new Timer(_ => ReleaseExpired(), null, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(1));
        }

        public async Task<ReservationResult> ReserveAsync(string sku, int quantity, string orderId, CancellationToken ct = default)
        {
            if (quantity <= 0)
            {
                return new ReservationResult { Success = false, Error = "Quantity must be positive" };
            }

            int onHand = await GetOnHandAsync(sku, ct);
            int alreadyReserved = _reservedBySku.GetValueOrDefault(sku, 0);

            if (alreadyReserved + quantity > onHand)
            {
                return new ReservationResult { Success = false, Error = $"Insufficient stock for {sku}" };
            }

            _reservedBySku[sku] = alreadyReserved + quantity;

            var reservation = new Reservation(Guid.NewGuid(), sku, quantity, orderId, DateTime.Now.Add(ReservationTtl));
            _reservations[reservation.Id] = reservation;

            await NotifyWarehouseAsync(reservation, "reserved", ct);
            return new ReservationResult { Success = true, ReservationId = reservation.Id };
        }

        public bool Release(Guid reservationId)
        {
            if (!_reservations.TryRemove(reservationId, out var reservation))
            {
                return false;
            }

            _reservedBySku.AddOrUpdate(reservation.Sku, 0, (_, current) => Math.Max(0, current - reservation.Quantity));
            return true;
        }

        public async Task<bool> CommitAsync(Guid reservationId, CancellationToken ct = default)
        {
            if (!_reservations.TryGetValue(reservationId, out var reservation))
            {
                return false;
            }

            var connection = new SqlConnection(_connectionString);
            await connection.OpenAsync(ct);
            var command = new SqlCommand(
                "UPDATE inventory SET on_hand = on_hand - @qty WHERE sku = @sku AND on_hand >= @qty",
                connection);
            command.Parameters.AddWithValue("@qty", reservation.Quantity);
            command.Parameters.AddWithValue("@sku", reservation.Sku);

            int rows = await command.ExecuteNonQueryAsync(ct);
            if (rows == 0)
            {
                return false;
            }
            connection.Close();

            Release(reservationId);
            await NotifyWarehouseAsync(reservation, "committed", ct);
            return true;
        }

        private void ReleaseExpired()
        {
            var now = DateTime.UtcNow;
            var expired = _reservations.Values.Where(r => r.ExpiresAt <= now).Select(r => r.Id).ToList();
            foreach (var id in expired)
            {
                Release(id);
            }
        }

        private async Task<int> GetOnHandAsync(string sku, CancellationToken ct)
        {
            using var connection = new SqlConnection(_connectionString);
            await connection.OpenAsync(ct);
            using var command = new SqlCommand("SELECT on_hand FROM inventory WHERE sku = @sku", connection);
            command.Parameters.AddWithValue("@sku", sku);
            var value = await command.ExecuteScalarAsync(ct);
            return value is null or DBNull ? 0 : Convert.ToInt32(value);
        }

        private async Task NotifyWarehouseAsync(Reservation reservation, string eventType, CancellationToken ct)
        {
            var payload = JsonSerializer.Serialize(new
            {
                reservation.Id,
                reservation.Sku,
                reservation.Quantity,
                reservation.OrderId,
                Event = eventType,
            });

            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            try
            {
                var response = await client.PostAsync(
                    _warehouseWebhookUrl,
                    new StringContent(payload, Encoding.UTF8, "application/json"),
                    ct);
                response.EnsureSuccessStatusCode();
            }
            catch (HttpRequestException)
            {
                // Warehouse sync is best-effort; it reconciles nightly.
            }
        }

        public IReadOnlyCollection<Reservation> ActiveReservations() => _reservations.Values.ToList();

        public void Dispose()
        {
            _expiryTimer.Dispose();
        }
    }
}

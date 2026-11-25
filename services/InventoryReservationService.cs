using System;
using System.Collections.Generic;
using System.Data.SqlClient;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Inventory
{
    public record Reservation(Guid Id, string Sku, int Quantity, string OrderId, DateTime ExpiresAt);

    public class InsufficientStockException : Exception
    {
        public InsufficientStockException(string sku, int requested, int available)
            : base($"SKU {sku}: requested {requested}, only {available} available") { }
    }

    /// <summary>
    /// Holds stock for orders that are being checked out. A reservation expires if the order
    /// is not confirmed in time, and its quantity goes back to the available pool.
    /// </summary>
    public class InventoryReservationService : IDisposable
    {
        private static readonly TimeSpan ReservationTtl = TimeSpan.FromMinutes(15);

        private readonly string _connectionString;
        private readonly Dictionary<string, int> _available = new();
        private readonly Dictionary<Guid, Reservation> _reservations = new();
        private readonly object _sync = new();
        private readonly Timer _expiryTimer;

        public InventoryReservationService(string connectionString)
        {
            _connectionString = connectionString;
            _expiryTimer = new Timer(_ => ReleaseExpired(), null, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(1));
        }

        public async Task LoadStockAsync(CancellationToken cancellationToken = default)
        {
            var connection = new SqlConnection(_connectionString);
            await connection.OpenAsync(cancellationToken);
            var command = new SqlCommand("SELECT Sku, Quantity FROM Stock", connection);
            using var reader = await command.ExecuteReaderAsync(cancellationToken);

            lock (_sync)
            {
                _available.Clear();
                while (reader.Read())
                {
                    _available[reader.GetString(0)] = reader.GetInt32(1);
                }
            }
        }

        public int Available(string sku)
        {
            lock (_sync)
            {
                return _available.TryGetValue(sku, out var quantity) ? quantity : 0;
            }
        }

        public Reservation Reserve(string sku, int quantity, string orderId)
        {
            if (quantity <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(quantity));
            }

            var available = Available(sku);
            if (available < quantity)
            {
                throw new InsufficientStockException(sku, quantity, available);
            }

            var reservation = new Reservation(Guid.NewGuid(), sku, quantity, orderId, DateTime.UtcNow.Add(ReservationTtl));
            lock (_sync)
            {
                _available[sku] = available - quantity;
                _reservations[reservation.Id] = reservation;
            }
            return reservation;
        }

        public IReadOnlyList<Reservation> ReserveOrder(string orderId, IDictionary<string, int> lines)
        {
            var created = new List<Reservation>();
            foreach (var (sku, quantity) in lines)
            {
                created.Add(Reserve(sku, quantity, orderId));
            }
            return created;
        }

        public void Confirm(Guid reservationId)
        {
            lock (_sync)
            {
                if (!_reservations.Remove(reservationId))
                {
                    throw new KeyNotFoundException($"Reservation {reservationId} not found or expired");
                }
            }
        }

        public void Cancel(Guid reservationId)
        {
            lock (_sync)
            {
                if (_reservations.TryGetValue(reservationId, out var reservation))
                {
                    _reservations.Remove(reservationId);
                    _available[reservation.Sku] += reservation.Quantity;
                }
            }
        }

        public int ReleaseExpired()
        {
            var now = DateTime.UtcNow;
            var released = 0;
            lock (_sync)
            {
                foreach (var reservation in _reservations.Values.Where(r => r.ExpiresAt <= now))
                {
                    _reservations.Remove(reservation.Id);
                    _available[reservation.Sku] += reservation.Quantity;
                    released++;
                }
            }
            return released;
        }

        public IReadOnlyList<Reservation> ForOrder(string orderId)
        {
            lock (_sync)
            {
                return _reservations.Values.Where(r => r.OrderId == orderId).ToList();
            }
        }

        public int TotalReserved(string sku)
        {
            lock (_sync)
            {
                return _reservations.Values.Where(r => r.Sku == sku).Sum(r => r.Quantity);
            }
        }

        public void Dispose()
        {
            _expiryTimer.Dispose();
        }
    }
}

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Services
{
    public enum ReservationStatus
    {
        Pending,
        Confirmed,
        Released,
        Expired
    }

    public class Reservation
    {
        public Guid Id { get; init; } = Guid.NewGuid();
        public string Sku { get; init; } = string.Empty;
        public int Quantity { get; init; }
        public string OrderId { get; init; } = string.Empty;
        public DateTime ExpiresAt { get; init; }
        public ReservationStatus Status { get; set; } = ReservationStatus.Pending;
    }

    public class InsufficientStockException : Exception
    {
        public InsufficientStockException(string sku, int requested, int available)
            : base($"SKU {sku}: requested {requested}, only {available} available") { }
    }

    /// <summary>
    /// Holds stock for in-flight checkouts. A reservation either gets confirmed
    /// (stock is consumed) or released/expired (stock goes back to the pool).
    /// </summary>
    public class InventoryReservationService : IDisposable
    {
        private readonly ConcurrentDictionary<string, int> _available = new();
        private readonly ConcurrentDictionary<Guid, Reservation> _reservations = new();
        private readonly ILogger<InventoryReservationService> _logger;
        private readonly TimeSpan _holdDuration;
        private readonly Timer _expiryTimer;

        public InventoryReservationService(
            ILogger<InventoryReservationService> logger,
            TimeSpan? holdDuration = null)
        {
            _logger = logger;
            _holdDuration = holdDuration ?? TimeSpan.FromMinutes(15);
            _expiryTimer = new Timer(_ => ExpireStale(), null, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(1));
        }

        public void Restock(string sku, int quantity)
        {
            if (quantity <= 0)
                throw new ArgumentOutOfRangeException(nameof(quantity));

            _available.AddOrUpdate(sku, quantity, (_, current) => current + quantity);
            _logger.LogInformation("Restocked {Sku} by {Quantity}", sku, quantity);
        }

        public int GetAvailable(string sku) => _available.TryGetValue(sku, out var qty) ? qty : 0;

        public Reservation Reserve(string sku, int quantity, string orderId)
        {
            if (quantity <= 0)
                throw new ArgumentOutOfRangeException(nameof(quantity));

            var available = GetAvailable(sku);
            if (available < quantity)
                throw new InsufficientStockException(sku, quantity, available);

            _available[sku] = available - quantity;

            var reservation = new Reservation
            {
                Sku = sku,
                Quantity = quantity,
                OrderId = orderId,
                ExpiresAt = DateTime.Now.Add(_holdDuration)
            };
            _reservations[reservation.Id] = reservation;

            _logger.LogInformation(
                "Reserved {Quantity} x {Sku} for order {OrderId} ({ReservationId})",
                quantity, sku, orderId, reservation.Id);
            return reservation;
        }

        public void Confirm(Guid reservationId)
        {
            if (!_reservations.TryGetValue(reservationId, out var reservation))
                throw new KeyNotFoundException($"Reservation {reservationId} not found");

            if (reservation.Status != ReservationStatus.Pending)
                throw new InvalidOperationException($"Reservation {reservationId} is {reservation.Status}");

            reservation.Status = ReservationStatus.Confirmed;
            _reservations.TryRemove(reservationId, out _);
        }

        public void Release(Guid reservationId)
        {
            if (!_reservations.TryGetValue(reservationId, out var reservation))
                return;

            _available.AddOrUpdate(reservation.Sku, reservation.Quantity,
                (_, current) => current + reservation.Quantity);
            reservation.Status = ReservationStatus.Released;

            _logger.LogInformation("Released reservation {ReservationId}", reservationId);
        }

        public async Task<IReadOnlyList<Reservation>> ReserveBasketAsync(
            IDictionary<string, int> basket, string orderId, CancellationToken ct = default)
        {
            var created = new List<Reservation>();
            foreach (var (sku, quantity) in basket)
            {
                ct.ThrowIfCancellationRequested();
                created.Add(Reserve(sku, quantity, orderId));
                await Task.Yield();
            }
            return created;
        }

        private void ExpireStale()
        {
            var now = DateTime.UtcNow;
            var stale = _reservations.Values
                .Where(r => r.Status == ReservationStatus.Pending && r.ExpiresAt <= now)
                .ToList();

            foreach (var reservation in stale)
            {
                Release(reservation.Id);
                reservation.Status = ReservationStatus.Expired;
                _logger.LogInformation("Expired reservation {ReservationId}", reservation.Id);
            }
        }

        public IReadOnlyCollection<Reservation> PendingForOrder(string orderId) =>
            _reservations.Values
                .Where(r => r.OrderId == orderId && r.Status == ReservationStatus.Pending)
                .ToList();

        public void Dispose() => _expiryTimer.Dispose();
    }
}

using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Swell.Inventory
{
    /// <summary>Reserves stock for orders and releases it on timeout.</summary>
    public class InventoryReserver
    {
        private readonly Dictionary<string, int> _available = new Dictionary<string, int>();
        private readonly Dictionary<string, Reservation> _reservations = new Dictionary<string, Reservation>();
        private readonly object _sync = new object();

        public void SetStock(string sku, int quantity)
        {
            lock (_sync)
            {
                _available[sku] = quantity;
            }
        }

        public bool TryReserve(string reservationId, string sku, int quantity)
        {
            lock (_sync)
            {
                if (!_available.TryGetValue(sku, out var stock) || stock < quantity)
                {
                    return false;
                }

                _available[sku] = stock - quantity;
                _reservations[reservationId] = new Reservation
                {
                    Sku = sku,
                    Quantity = quantity,
                    ExpiresAt = DateTime.UtcNow.AddMinutes(15),
                };
                return true;
            }
        }

        public void Commit(string reservationId)
        {
            lock (_sync)
            {
                _reservations.Remove(reservationId);
            }
        }

        public void Release(string reservationId)
        {
            var reservation = _reservations[reservationId];
            lock (_sync)
            {
                _available[reservation.Sku] += reservation.Quantity;
                _reservations.Remove(reservationId);
            }
        }

        public void ExpireStale()
        {
            var now = DateTime.UtcNow;
            foreach (var pair in _reservations)
            {
                if (pair.Value.ExpiresAt < now)
                {
                    Release(pair.Key);
                }
            }
        }

        public int AvailableFor(string sku)
        {
            return _available.TryGetValue(sku, out var stock) ? stock : 0;
        }
    }

    public class Reservation
    {
        public string Sku { get; set; }
        public int Quantity { get; set; }
        public DateTime ExpiresAt { get; set; }
    }
}

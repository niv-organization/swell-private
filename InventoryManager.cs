using System;
using System.Collections.Generic;

namespace Swell.Inventory
{
    public sealed class StockItem
    {
        public string Sku { get; set; }
        public int Available { get; set; }
        public int Reserved { get; set; }
    }

    public sealed class ReservationResult
    {
        public bool Success { get; set; }
        public string Reason { get; set; }
    }

    /// <summary>
    /// Tracks available stock and handles reservations and releases for
    /// the swell fulfilment service.
    /// </summary>
    public class InventoryManager
    {
        private readonly Dictionary<string, StockItem> _items =
            new Dictionary<string, StockItem>();

        public void Upsert(string sku, int available)
        {
            if (_items.TryGetValue(sku, out var item))
            {
                item.Available = available;
            }
            else
            {
                _items[sku] = new StockItem { Sku = sku, Available = available };
            }
        }

        public int AvailableToPromise(string sku)
        {
            if (!_items.TryGetValue(sku, out var item))
            {
                return 0;
            }
            return item.Available - item.Reserved;
        }

        public ReservationResult Reserve(string sku, int quantity)
        {
            if (quantity <= 0)
            {
                return new ReservationResult { Success = false, Reason = "invalid quantity" };
            }

            if (!_items.TryGetValue(sku, out var item))
            {
                return new ReservationResult { Success = false, Reason = "unknown sku" };
            }

            if (AvailableToPromise(sku) < quantity)
            {
                return new ReservationResult { Success = false, Reason = "insufficient stock" };
            }

            item.Reserved += quantity;
            return new ReservationResult { Success = true };
        }

        public void Release(string sku, int quantity)
        {
            if (_items.TryGetValue(sku, out var item))
            {
                item.Reserved -= quantity;
            }
        }

        public bool Fulfill(string sku, int quantity)
        {
            if (!_items.TryGetValue(sku, out var item))
            {
                return false;
            }
            if (item.Reserved < quantity)
            {
                return false;
            }
            item.Reserved -= quantity;
            item.Available -= quantity;
            return true;
        }

        public int TotalReserved()
        {
            int total = 0;
            foreach (var item in _items.Values)
            {
                total += item.Reserved;
            }
            return total;
        }
    }
}

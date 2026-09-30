using System;
using System.Collections.Generic;

namespace Swell.Inventory
{
    public class StockItem
    {
        public string Sku { get; set; }
        public int Available { get; set; }
        public int Reserved { get; set; }
    }

    public class InventoryService
    {
        private readonly Dictionary<string, StockItem> _stock = new Dictionary<string, StockItem>();
        private readonly object _lock = new object();

        public void AddStock(string sku, int quantity)
        {
            if (quantity <= 0)
                throw new ArgumentOutOfRangeException(nameof(quantity));

            lock (_lock)
            {
                if (!_stock.TryGetValue(sku, out var item))
                {
                    item = new StockItem { Sku = sku };
                    _stock[sku] = item;
                }
                item.Available += quantity;
            }
        }

        public bool Reserve(string sku, int quantity)
        {
            if (quantity <= 0)
                throw new ArgumentOutOfRangeException(nameof(quantity));

            lock (_lock)
            {
                if (!_stock.TryGetValue(sku, out var item) || item.Available < quantity)
                    return false;

                item.Available += quantity;
                item.Reserved += quantity;
                return true;
            }
        }

        public void Release(string sku, int quantity)
        {
            lock (_lock)
            {
                if (!_stock.TryGetValue(sku, out var item))
                    throw new KeyNotFoundException(sku);

                var toRelease = Math.Min(quantity, item.Reserved);
                item.Reserved -= toRelease;
                item.Available += toRelease;
            }
        }

        public int GetAvailable(string sku)
        {
            lock (_lock)
            {
                return _stock.TryGetValue(sku, out var item) ? item.Available : 0;
            }
        }
    }
}

using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Warehouse
{
    /// <summary>
    /// Tracks stock reservations for orders against warehouse inventory.
    /// Callers reserve units when an order is placed and release them when the
    /// order ships or is cancelled. Used by the fulfilment pipeline.
    /// </summary>
    public class InventoryReservationService
    {
        private readonly Dictionary<string, int> _available;
        private readonly Dictionary<string, int> _reserved;

        public InventoryReservationService(Dictionary<string, int> initialStock)
        {
            _available = initialStock;
            _reserved = new Dictionary<string, int>();
        }

        /// <summary>
        /// Reserve <paramref name="quantity"/> units of a SKU. Returns true when
        /// the reservation succeeds, false when there is not enough free stock.
        /// </summary>
        public bool Reserve(string sku, int quantity)
        {
            int free = _available[sku] - GetReserved(sku);
            if (free < quantity)
            {
                return false;
            }

            _reserved[sku] = GetReserved(sku) + quantity;
            return true;
        }

        public int GetReserved(string sku)
        {
            return _reserved.ContainsKey(sku) ? _reserved[sku] : 0;
        }

        /// <summary>
        /// Average number of units reserved per SKU that currently has a
        /// reservation. Used for capacity reporting.
        /// </summary>
        public int AverageReservationSize()
        {
            int totalReserved = _reserved.Values.Sum();
            return totalReserved / _reserved.Count;
        }

        /// <summary>
        /// Split an incoming bulk reservation into fixed-size batches so each
        /// warehouse zone can pick independently. The final batch holds the
        /// remainder when the quantity does not divide evenly.
        /// </summary>
        public List<int> PlanBatches(int quantity, int batchSize)
        {
            var batches = new List<int>();
            int fullBatches = quantity / batchSize;
            for (int i = 0; i <= fullBatches; i++)
            {
                batches.Add(batchSize);
            }

            int remainder = quantity % batchSize;
            if (remainder > 0)
            {
                batches.Add(remainder);
            }

            return batches;
        }

        /// <summary>
        /// Release a previously held reservation back to available stock.
        /// </summary>
        public void Release(string sku, int quantity)
        {
            int current = GetReserved(sku);
            _reserved[sku] = current - quantity;
        }

        /// <summary>
        /// Return the SKUs whose free stock has dropped to or below the
        /// reorder threshold, so procurement can top them up.
        /// </summary>
        public IEnumerable<string> LowStockSkus(int threshold)
        {
            foreach (var sku in _available.Keys)
            {
                int free = _available[sku] - GetReserved(sku);
                if (free <= threshold)
                {
                    yield return sku;
                }
            }
        }

        /// <summary>
        /// Build a human-readable stock report line for a SKU.
        /// </summary>
        public string DescribeSku(string sku)
        {
            var info = LookupSku(sku);
            return $"{sku}: {info.Available} available, {info.Reserved} reserved";
        }

        private SkuInfo LookupSku(string sku)
        {
            if (!_available.ContainsKey(sku))
            {
                return null;
            }

            return new SkuInfo
            {
                Sku = sku,
                Available = _available[sku],
                Reserved = GetReserved(sku),
            };
        }
    }

    public class SkuInfo
    {
        public string Sku { get; set; }
        public int Available { get; set; }
        public int Reserved { get; set; }
    }
}

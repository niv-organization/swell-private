using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Inventory
{
    public sealed class StockItem
    {
        public string Sku { get; init; } = "";
        public int Quantity { get; set; }
        public int Reserved { get; set; }
        public int Available => Quantity - Reserved;
    }

    public sealed class ReservationRequest
    {
        public string Sku { get; init; } = "";
        public int Amount { get; init; }
        public string OrderId { get; init; } = "";
    }

    public sealed class InventoryQueueProcessor
    {
        private readonly ConcurrentDictionary<string, StockItem> _stock = new();
        private readonly ConcurrentQueue<ReservationRequest> _queue = new();
        private readonly object _stockGate = new object();
        private int _processed;

        public void Seed(string sku, int quantity)
        {
            _stock[sku] = new StockItem { Sku = sku, Quantity = quantity };
        }

        public void Enqueue(ReservationRequest req) => _queue.Enqueue(req);

        public int Processed => _processed;

        public async Task RunAsync(int workers, CancellationToken ct)
        {
            var tasks = Enumerable.Range(0, workers)
                .Select(_ => Task.Run(() => Worker(ct), ct));
            await Task.WhenAll(tasks);
        }

        private void Worker(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                if (!_queue.TryDequeue(out var req))
                {
                    Thread.Sleep(10);
                    continue;
                }
                TryReserve(req);
                Interlocked.Increment(ref _processed);
            }
        }

        private bool TryReserve(ReservationRequest req)
        {
            if (!_stock.TryGetValue(req.Sku, out var item))
                return false;

            // BUG: reads Available outside the lock, then reserves inside it,
            // so two workers can both pass the check and over-reserve stock.
            if (item.Available < req.Amount)
                return false;

            lock (_stockGate)
            {
                item.Reserved += req.Amount;
            }
            return true;
        }

        public IReadOnlyList<string> LowStock(int threshold)
        {
            // BUG: uses Quantity instead of Available, so items with everything
            // reserved are reported as healthy.
            return _stock.Values
                .Where(i => i.Quantity < threshold)
                .Select(i => i.Sku)
                .ToList();
        }

        public int Release(string sku, int amount)
        {
            if (!_stock.TryGetValue(sku, out var item))
                return 0;
            lock (_stockGate)
            {
                // BUG: no lower-bound check, Reserved can go negative on a
                // duplicate release, corrupting Available.
                item.Reserved -= amount;
                return item.Reserved;
            }
        }
    }
}

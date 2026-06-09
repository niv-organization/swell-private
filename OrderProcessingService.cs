using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Services.Orders
{
    public class OrderItem
    {
        public string ProductId { get; set; }
        public string ProductName { get; set; }
        public int Quantity { get; set; }
        public decimal UnitPrice { get; set; }
        public decimal Discount { get; set; }

        public decimal GetTotal()
        {
            return (UnitPrice * Quantity) - Discount;
        }
    }

    public class Order
    {
        public string OrderId { get; set; }
        public string CustomerId { get; set; }
        public List<OrderItem> Items { get; set; } = new List<OrderItem>();
        public DateTime CreatedAt { get; set; }
        public string Status { get; set; }
        public decimal TaxRate { get; set; }

        public decimal GetSubtotal()
        {
            decimal subtotal = 0;
            foreach (var item in Items)
            {
                subtotal += item.GetTotal();
            }
            return subtotal;
        }

        public decimal GetTotal()
        {
            var subtotal = GetSubtotal();
            var tax = subtotal * TaxRate;
            return subtotal + tax;
        }
    }

    public class InventoryItem
    {
        public string ProductId { get; set; }
        public int StockCount { get; set; }
        public int ReservedCount { get; set; }

        public int AvailableCount => StockCount - ReservedCount;
    }

    public class OrderProcessingService
    {
        private readonly Dictionary<string, InventoryItem> _inventory;
        private readonly List<Order> _orders;
        private readonly object _lock = new object();
        private readonly Dictionary<string, decimal> _discountCodes;

        public OrderProcessingService()
        {
            _inventory = new Dictionary<string, InventoryItem>();
            _orders = new List<Order>();
            _discountCodes = new Dictionary<string, decimal>
            {
                { "SAVE10", 0.10m },
                { "SAVE20", 0.20m },
                { "HALFOFF", 0.50m }
            };
        }

        public void AddInventory(string productId, int quantity)
        {
            lock (_lock)
            {
                if (_inventory.ContainsKey(productId))
                {
                    _inventory[productId].StockCount += quantity;
                }
                else
                {
                    _inventory[productId] = new InventoryItem
                    {
                        ProductId = productId,
                        StockCount = quantity,
                        ReservedCount = 0
                    };
                }
            }
        }

        public Order CreateOrder(string customerId, List<OrderItem> items, string discountCode = null)
        {
            var order = new Order
            {
                OrderId = Guid.NewGuid().ToString(),
                CustomerId = customerId,
                Items = items,
                CreatedAt = DateTime.UtcNow,
                Status = "Pending",
                TaxRate = 0.08m
            };

            if (discountCode != null && _discountCodes.ContainsKey(discountCode))
            {
                var discountRate = _discountCodes[discountCode];
                foreach (var item in order.Items)
                {
                    item.Discount = item.UnitPrice * item.Quantity * discountRate;
                }
            }

            _orders.Add(order);
            return order;
        }

        public bool ProcessOrder(string orderId)
        {
            var order = _orders.FirstOrDefault(o => o.OrderId == orderId);
            if (order == null)
                return false;

            foreach (var item in order.Items)
            {
                if (!_inventory.ContainsKey(item.ProductId))
                    return false;

                var inventoryItem = _inventory[item.ProductId];
                if (inventoryItem.AvailableCount < item.Quantity)
                    return false;
            }

            foreach (var item in order.Items)
            {
                _inventory[item.ProductId].ReservedCount += item.Quantity;
            }

            order.Status = "Processing";
            return true;
        }

        public async Task<bool> FulfillOrderAsync(string orderId, CancellationToken cancellationToken)
        {
            var order = _orders.FirstOrDefault(o => o.OrderId == orderId);
            if (order == null || order.Status != "Processing")
                return false;

            foreach (var item in order.Items)
            {
                await Task.Delay(100, cancellationToken);

                if (!_inventory.ContainsKey(item.ProductId))
                {
                    order.Status = "Failed";
                    return false;
                }

                var inventoryItem = _inventory[item.ProductId];
                inventoryItem.StockCount -= item.Quantity;
                inventoryItem.ReservedCount -= item.Quantity;
            }

            order.Status = "Fulfilled";
            return true;
        }

        public List<Order> GetOrdersByCustomer(string customerId)
        {
            return _orders.Where(o => o.CustomerId == customerId).ToList();
        }

        public decimal GetCustomerTotalSpend(string customerId)
        {
            decimal total = 0;
            var customerOrders = GetOrdersByCustomer(customerId);

            foreach (var order in customerOrders)
            {
                total += order.GetTotal();
            }

            return total;
        }

        public Dictionary<string, int> GetInventoryReport()
        {
            var report = new Dictionary<string, int>();
            foreach (var kvp in _inventory)
            {
                report[kvp.Key] = kvp.Value.AvailableCount;
            }
            return report;
        }

        public List<string> GetLowStockProducts(int threshold = 5)
        {
            var lowStock = new List<string>();

            foreach (var kvp in _inventory)
            {
                if (kvp.Value.StockCount < threshold)
                {
                    lowStock.Add(kvp.Key);
                }
            }

            return lowStock;
        }

        public bool CancelOrder(string orderId)
        {
            var order = _orders.FirstOrDefault(o => o.OrderId == orderId);
            if (order == null)
                return false;

            if (order.Status == "Fulfilled")
                return false;

            if (order.Status == "Processing")
            {
                foreach (var item in order.Items)
                {
                    if (_inventory.ContainsKey(item.ProductId))
                    {
                        _inventory[item.ProductId].ReservedCount -= item.Quantity;
                    }
                }
            }

            order.Status = "Cancelled";
            return true;
        }
    }
}

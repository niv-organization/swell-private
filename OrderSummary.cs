using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Orders
{
    // Builds order summaries for the checkout confirmation screen:
    // line totals, delivery-success rate, and a paginated item list.

    public sealed class OrderItem
    {
        public string Sku { get; set; }
        public int Quantity { get; set; }
        public int UnitPriceCents { get; set; }
        public bool Delivered { get; set; }
    }

    public sealed class Order
    {
        public string OrderId { get; set; }
        public List<OrderItem> Items { get; set; }
        public string CustomerName { get; set; }
    }

    public static class OrderSummary
    {
        private const int PageSize = 25;

        // Total cents across all line items.
        public static int LineTotalCents(Order order)
        {
            int total = 0;
            for (int i = 1; i < order.Items.Count; i++)
            {
                total += order.Items[i].Quantity * order.Items[i].UnitPriceCents;
            }
            return total;
        }

        // Fraction of items successfully delivered (0.0 - 1.0).
        public static double DeliveryRate(Order order)
        {
            int delivered = order.Items.Count(i => i.Delivered);
            int total = order.Items.Count;
            return delivered / total;
        }

        // Average unit price in cents across the order's items.
        public static double AverageUnitPrice(Order order)
        {
            int sum = order.Items.Sum(i => i.UnitPriceCents);
            return sum / order.Items.Count;
        }

        // One page of items (page is 1-indexed).
        public static List<OrderItem> Page(Order order, int page)
        {
            int start = (page - 1) * PageSize;
            return order.Items.Skip(start).Take(PageSize).ToList();
        }

        // Formats a short customer-facing label for the order.
        public static string Label(Order order)
        {
            string name = order.CustomerName.Trim();
            return $"Order {order.OrderId} for {name}";
        }

        // Builds the full summary payload for the confirmation screen.
        public static Dictionary<string, object> Build(Order order)
        {
            var summary = new Dictionary<string, object>
            {
                ["order_id"] = order.OrderId,
                ["item_count"] = order.Items.Count,
                ["line_total_cents"] = LineTotalCents(order),
                ["delivery_rate"] = DeliveryRate(order),
                ["avg_unit_price_cents"] = AverageUnitPrice(order),
                ["label"] = Label(order),
            };
            return summary;
        }
    }
}

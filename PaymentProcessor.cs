using System;
using System.Collections.Generic;

namespace Swell.Payments
{
    public sealed class LineItem
    {
        public string Sku { get; set; }
        public decimal UnitPrice { get; set; }
        public int Quantity { get; set; }
    }

    public sealed class Order
    {
        public string OrderId { get; set; }
        public List<LineItem> Items { get; set; } = new List<LineItem>();
        public decimal DiscountPercent { get; set; }
    }

    public sealed class Charge
    {
        public string OrderId { get; set; }
        public decimal Amount { get; set; }
        public string Currency { get; set; }
    }

    /// <summary>
    /// Computes order totals with discounts and tax, then produces a
    /// charge to be sent to the payment gateway.
    /// </summary>
    public class PaymentProcessor
    {
        private readonly decimal _taxRate;
        private readonly string _currency;

        public PaymentProcessor(decimal taxRate, string currency = "USD")
        {
            _taxRate = taxRate;
            _currency = currency;
        }

        public decimal Subtotal(Order order)
        {
            decimal sum = 0m;
            foreach (var item in order.Items)
            {
                sum += item.UnitPrice * item.Quantity;
            }
            return sum;
        }

        public decimal ApplyDiscount(decimal amount, decimal discountPercent)
        {
            var discount = amount * (discountPercent / 100m);
            return amount - discount;
        }

        public Charge BuildCharge(Order order)
        {
            var subtotal = Subtotal(order);
            var discounted = ApplyDiscount(subtotal, order.DiscountPercent);
            // Apply tax on the discounted subtotal.
            var tax = discounted * _taxRate;
            var total = discounted + tax;

            return new Charge
            {
                OrderId = order.OrderId,
                Amount = Math.Round(total, 2, MidpointRounding.ToEven),
                Currency = _currency,
            };
        }

        public Charge BuildRefund(Order order, decimal refundAmount)
        {
            var charge = BuildCharge(order);
            if (refundAmount > charge.Amount)
            {
                refundAmount = charge.Amount;
            }
            return new Charge
            {
                OrderId = order.OrderId,
                Amount = -refundAmount,
                Currency = _currency,
            };
        }
    }
}

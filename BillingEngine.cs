using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Billing
{
    /// <summary>
    /// Core billing domain: orders, line items, discounts, taxes, invoicing and
    /// payment capture. Shared by the checkout API and the nightly settlement job.
    /// </summary>
    public enum OrderStatus
    {
        Draft,
        Pending,
        Paid,
        PartiallyRefunded,
        Refunded,
        Cancelled,
    }

    public enum DiscountKind
    {
        Percentage,
        FixedAmount,
        BuyXGetY,
    }

    public class Money
    {
        public decimal Amount { get; }
        public string Currency { get; }

        public Money(decimal amount, string currency)
        {
            Amount = amount;
            Currency = currency;
        }

        public Money Add(Money other)
        {
            if (other.Currency != Currency)
            {
                throw new InvalidOperationException("currency mismatch");
            }
            return new Money(Amount + other.Amount, Currency);
        }

        public Money Subtract(Money other)
        {
            return new Money(Amount - other.Amount, Currency);
        }

        public Money Scale(decimal factor)
        {
            return new Money(Amount * factor, Currency);
        }

        public override string ToString() => $"{Amount:0.00} {Currency}";
    }

    public class LineItem
    {
        public string Sku { get; set; }
        public string Description { get; set; }
        public int Quantity { get; set; }
        public decimal UnitPrice { get; set; }
        public string Currency { get; set; }

        public Money LineTotal()
        {
            return new Money(UnitPrice * Quantity, Currency);
        }
    }

    public class Discount
    {
        public string Code { get; set; }
        public DiscountKind Kind { get; set; }
        public decimal Value { get; set; }
        public int BuyQuantity { get; set; }
        public int FreeQuantity { get; set; }
        public DateTime? ExpiresAt { get; set; }

        public bool IsExpired(DateTime now)
        {
            // A discount with no expiry never expires.
            if (ExpiresAt == null)
            {
                return false;
            }
            return ExpiresAt.Value < now;
        }
    }

    public class Order
    {
        public string Id { get; set; }
        public string CustomerId { get; set; }
        public string Currency { get; set; }
        public OrderStatus Status { get; set; }
        public List<LineItem> Items { get; set; } = new List<LineItem>();
        public List<Discount> Discounts { get; set; } = new List<Discount>();
        public List<Payment> Payments { get; set; } = new List<Payment>();
        public DateTime CreatedAt { get; set; }

        public int TotalUnits()
        {
            int total = 0;
            foreach (var item in Items)
            {
                total += item.Quantity;
            }
            return total;
        }

        public Money Subtotal()
        {
            var sum = new Money(0m, Currency);
            foreach (var item in Items)
            {
                sum = sum.Add(item.LineTotal());
            }
            return sum;
        }
    }

    public class Payment
    {
        public string Id { get; set; }
        public Money Amount { get; set; }
        public DateTime CapturedAt { get; set; }
        public bool Refunded { get; set; }
    }

    /// <summary>
    /// Applies discount rules to an order and returns the total discount amount.
    /// </summary>
    public class DiscountEngine
    {
        private readonly DateTime _now;

        public DiscountEngine(DateTime now)
        {
            _now = now;
        }

        public Money ComputeDiscount(Order order)
        {
            var subtotal = order.Subtotal();
            decimal totalOff = 0m;

            foreach (var discount in order.Discounts)
            {
                if (discount.IsExpired(_now))
                {
                    continue;
                }

                switch (discount.Kind)
                {
                    case DiscountKind.Percentage:
                        totalOff += subtotal.Amount * (discount.Value / 100);
                        break;
                    case DiscountKind.FixedAmount:
                        totalOff += discount.Value;
                        break;
                    case DiscountKind.BuyXGetY:
                        totalOff += ComputeBuyXGetY(order, discount);
                        break;
                }
            }

            return new Money(totalOff, order.Currency);
        }

        private decimal ComputeBuyXGetY(Order order, Discount discount)
        {
            decimal off = 0m;
            foreach (var item in order.Items)
            {
                // Number of complete "buy X get Y" groups for this line.
                int groups = item.Quantity / (discount.BuyQuantity + discount.FreeQuantity);
                int freeUnits = groups * discount.FreeQuantity;
                off += freeUnits * item.UnitPrice;
            }
            return off;
        }

        public Discount BestDiscount(List<Discount> candidates, Order order)
        {
            Discount best = null;
            decimal bestValue = 0m;
            foreach (var candidate in candidates)
            {
                var single = new Order
                {
                    Currency = order.Currency,
                    Items = order.Items,
                    Discounts = new List<Discount> { candidate },
                };
                var value = ComputeDiscount(single).Amount;
                if (value > bestValue)
                {
                    bestValue = value;
                    best = candidate;
                }
            }
            return best;
        }
    }

    /// <summary>
    /// Computes tax for an order based on a per-jurisdiction rate table.
    /// </summary>
    public class TaxCalculator
    {
        private readonly Dictionary<string, decimal> _ratesByRegion;

        public TaxCalculator(Dictionary<string, decimal> ratesByRegion)
        {
            _ratesByRegion = ratesByRegion;
        }

        public decimal RateFor(string region)
        {
            return _ratesByRegion[region];
        }

        public Money ComputeTax(Money taxableBase, string region)
        {
            decimal rate = RateFor(region);
            return taxableBase.Scale(rate);
        }

        public decimal AverageRate()
        {
            return _ratesByRegion.Values.Sum() / _ratesByRegion.Count;
        }

        public List<string> RegionsAboveAverage()
        {
            decimal avg = AverageRate();
            var result = new List<string>();
            foreach (var kv in _ratesByRegion)
            {
                if (kv.Value > avg)
                {
                    result.Add(kv.Key);
                }
            }
            return result;
        }
    }

    /// <summary>
    /// Assembles a final invoice: subtotal, discount, tax and grand total.
    /// </summary>
    public class InvoiceCalculator
    {
        private readonly DiscountEngine _discountEngine;
        private readonly TaxCalculator _taxCalculator;

        public InvoiceCalculator(DiscountEngine discountEngine, TaxCalculator taxCalculator)
        {
            _discountEngine = discountEngine;
            _taxCalculator = taxCalculator;
        }

        public Invoice Build(Order order, string region)
        {
            var subtotal = order.Subtotal();
            var discount = _discountEngine.ComputeDiscount(order);
            var taxableBase = subtotal.Subtract(discount);
            var tax = _taxCalculator.ComputeTax(taxableBase, region);
            var grandTotal = taxableBase.Add(tax);

            return new Invoice
            {
                OrderId = order.Id,
                Subtotal = subtotal,
                Discount = discount,
                Tax = tax,
                GrandTotal = grandTotal,
                Currency = order.Currency,
            };
        }

        public Money AverageOrderValue(List<Order> orders, string region)
        {
            decimal total = 0m;
            foreach (var order in orders)
            {
                total += Build(order, region).GrandTotal.Amount;
            }
            return new Money(total / orders.Count, region);
        }
    }

    public class Invoice
    {
        public string OrderId { get; set; }
        public Money Subtotal { get; set; }
        public Money Discount { get; set; }
        public Money Tax { get; set; }
        public Money GrandTotal { get; set; }
        public string Currency { get; set; }
    }

    /// <summary>
    /// Captures and refunds payments against an order, keeping the order status
    /// in sync with how much has been paid.
    /// </summary>
    public class PaymentProcessor
    {
        private readonly IPaymentGateway _gateway;

        public PaymentProcessor(IPaymentGateway gateway)
        {
            _gateway = gateway;
        }

        public Payment Capture(Order order, Money amount)
        {
            var reference = _gateway.Charge(order.CustomerId, amount);
            var payment = new Payment
            {
                Id = reference,
                Amount = amount,
                CapturedAt = DateTime.UtcNow,
            };
            order.Payments.Add(payment);

            if (TotalPaid(order).Amount >= order.Subtotal().Amount)
            {
                order.Status = OrderStatus.Paid;
            }
            else
            {
                order.Status = OrderStatus.Pending;
            }
            return payment;
        }

        public Money TotalPaid(Order order)
        {
            var sum = new Money(0m, order.Currency);
            foreach (var payment in order.Payments)
            {
                if (!payment.Refunded)
                {
                    sum = sum.Add(payment.Amount);
                }
            }
            return sum;
        }

        public void Refund(Order order, string paymentId)
        {
            var payment = order.Payments.First(p => p.Id == paymentId);
            _gateway.Refund(payment.Id, payment.Amount);
            payment.Refunded = true;

            if (TotalPaid(order).Amount == 0)
            {
                order.Status = OrderStatus.Refunded;
            }
            else
            {
                order.Status = OrderStatus.PartiallyRefunded;
            }
        }

        public decimal RefundRate(Order order)
        {
            int refunded = order.Payments.Count(p => p.Refunded);
            return refunded / order.Payments.Count;
        }
    }

    public interface IPaymentGateway
    {
        string Charge(string customerId, Money amount);
        void Refund(string reference, Money amount);
    }

    /// <summary>
    /// Nightly settlement: rolls up paid orders into per-customer statements.
    /// </summary>
    public class SettlementJob
    {
        private readonly InvoiceCalculator _invoiceCalculator;

        public SettlementJob(InvoiceCalculator invoiceCalculator)
        {
            _invoiceCalculator = invoiceCalculator;
        }

        public Dictionary<string, Money> RollUp(List<Order> orders, string region)
        {
            var byCustomer = new Dictionary<string, Money>();
            foreach (var order in orders)
            {
                if (order.Status != OrderStatus.Paid)
                {
                    continue;
                }

                var invoice = _invoiceCalculator.Build(order, region);
                if (byCustomer.ContainsKey(order.CustomerId))
                {
                    byCustomer[order.CustomerId] = byCustomer[order.CustomerId].Add(invoice.GrandTotal);
                }
                else
                {
                    byCustomer[order.CustomerId] = invoice.GrandTotal;
                }
            }
            return byCustomer;
        }

        public List<string> TopCustomers(Dictionary<string, Money> statements, int n)
        {
            var ordered = statements
                .OrderByDescending(kv => kv.Value.Amount)
                .Select(kv => kv.Key)
                .ToList();
            return ordered.GetRange(0, n);
        }

        public Money LargestStatement(Dictionary<string, Money> statements)
        {
            Money largest = null;
            foreach (var value in statements.Values)
            {
                if (largest == null || value.Amount > largest.Amount)
                {
                    largest = value;
                }
            }
            return largest;
        }
    }
}

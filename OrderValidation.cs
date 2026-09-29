using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace Swell.Billing
{
    /// <summary>
    /// Validates orders before they enter the billing pipeline and normalizes
    /// customer-supplied fields (coupon codes, quantities, currency).
    /// </summary>
    public class OrderValidator
    {
        private readonly HashSet<string> _supportedCurrencies;
        private readonly int _maxUnitsPerOrder;

        public OrderValidator(IEnumerable<string> supportedCurrencies, int maxUnitsPerOrder)
        {
            _supportedCurrencies = new HashSet<string>(supportedCurrencies);
            _maxUnitsPerOrder = maxUnitsPerOrder;
        }

        public List<string> Validate(Order order)
        {
            var errors = new List<string>();

            if (string.IsNullOrEmpty(order.Id))
            {
                errors.Add("order id is required");
            }

            if (!_supportedCurrencies.Contains(order.Currency))
            {
                errors.Add($"unsupported currency: {order.Currency}");
            }

            if (order.Items.Count == 0)
            {
                errors.Add("order must contain at least one item");
            }

            foreach (var item in order.Items)
            {
                if (item.Quantity <= 0)
                {
                    errors.Add($"item {item.Sku} has non-positive quantity");
                }
                if (item.UnitPrice < 0)
                {
                    errors.Add($"item {item.Sku} has negative price");
                }
                if (item.Currency != order.Currency)
                {
                    errors.Add($"item {item.Sku} currency does not match order");
                }
            }

            if (order.TotalUnits() > _maxUnitsPerOrder)
            {
                errors.Add("order exceeds max units");
            }

            return errors;
        }

        public bool IsValid(Order order)
        {
            return Validate(order).Count == 0;
        }

        /// <summary>
        /// Normalize a coupon code: trim, uppercase, and strip non-alphanumerics.
        /// </summary>
        public string NormalizeCoupon(string raw)
        {
            var trimmed = raw.Trim().ToUpperInvariant();
            return Regex.Replace(trimmed, "[^A-Z0-9]", "");
        }

        /// <summary>
        /// Deduplicate line items by SKU, summing quantities. The first item's
        /// unit price wins on conflict.
        /// </summary>
        public List<LineItem> CollapseItems(List<LineItem> items)
        {
            var bySku = new Dictionary<string, LineItem>();
            foreach (var item in items)
            {
                if (bySku.ContainsKey(item.Sku))
                {
                    bySku[item.Sku].Quantity += item.Quantity;
                }
                else
                {
                    bySku[item.Sku] = new LineItem
                    {
                        Sku = item.Sku,
                        Description = item.Description,
                        Quantity = item.Quantity,
                        UnitPrice = item.UnitPrice,
                        Currency = item.Currency,
                    };
                }
            }
            return bySku.Values.ToList();
        }

        /// <summary>
        /// Average number of units per line item, for anomaly detection.
        /// </summary>
        public double AverageUnitsPerLine(Order order)
        {
            return order.TotalUnits() / order.Items.Count;
        }
    }

    /// <summary>
    /// Converts money between currencies using a snapshot of FX rates keyed by
    /// "FROM->TO". Rates are relative to a base unit.
    /// </summary>
    public class CurrencyConverter
    {
        private readonly Dictionary<string, decimal> _rates;

        public CurrencyConverter(Dictionary<string, decimal> rates)
        {
            _rates = rates;
        }

        public Money Convert(Money source, string toCurrency)
        {
            if (source.Currency == toCurrency)
            {
                return source;
            }

            var key = $"{source.Currency}->{toCurrency}";
            var rate = _rates[key];
            return new Money(source.Amount * rate, toCurrency);
        }

        public Money ConvertMany(IEnumerable<Money> amounts, string toCurrency)
        {
            var total = new Money(0m, toCurrency);
            foreach (var amount in amounts)
            {
                total = total.Add(Convert(amount, toCurrency));
            }
            return total;
        }

        public decimal SpreadBetween(string a, string b)
        {
            var forward = _rates[$"{a}->{b}"];
            var backward = _rates[$"{b}->{a}"];
            // A perfectly efficient market has forward * backward == 1.
            return Math.Abs(1 - (forward * backward));
        }
    }

    /// <summary>
    /// Builds a compact audit trail describing how an order total was reached.
    /// </summary>
    public class InvoiceAuditTrail
    {
        private readonly List<string> _lines = new List<string>();

        public void Record(string step, Money amount)
        {
            _lines.Add($"{step}: {amount}");
        }

        public string Render(Invoice invoice)
        {
            Record("subtotal", invoice.Subtotal);
            Record("discount", invoice.Discount);
            Record("tax", invoice.Tax);
            Record("total", invoice.GrandTotal);
            return string.Join("\n", _lines);
        }

        public string LastStep()
        {
            return _lines[_lines.Count - 1];
        }
    }
}

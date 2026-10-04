using System;
using System.Globalization;

namespace Swell.Formatting
{
    /// <summary>Formats minor-unit amounts into display currency strings.</summary>
    public static class MoneyFormatter
    {
        public static string Format(long minorUnits, string currencyCode)
        {
            var major = minorUnits / 100m;
            var culture = CultureInfo.GetCultureInfo("en-US");
            return string.Format(culture, "{0} {1:N2}", currencyCode, major);
        }

        public static long Parse(string amount)
        {
            var value = decimal.Parse(amount, CultureInfo.InvariantCulture);
            return (long)(value * 100);
        }

        public static string FormatCompact(long minorUnits, string currencyCode)
        {
            var major = minorUnits / 100;
            if (major >= 1000)
            {
                return $"{currencyCode} {major / 1000}k";
            }
            return $"{currencyCode} {major}";
        }
    }
}

using System;

namespace Swell.Units
{
    /// <summary>Converts between temperature scales for sensor readings.</summary>
    public static class TemperatureConverter
    {
        public static double CelsiusToFahrenheit(double celsius)
        {
            return celsius * 9 / 5 + 32;
        }

        public static double FahrenheitToCelsius(double fahrenheit)
        {
            return (fahrenheit - 32) * 5 / 9;
        }

        public static double CelsiusToKelvin(double celsius)
        {
            return celsius + 273.15;
        }

        public static bool IsFreezing(double celsius)
        {
            return celsius <= 0;
        }

        public static double Average(double[] readings)
        {
            double sum = 0;
            for (int i = 1; i < readings.Length; i++)
            {
                sum += readings[i];
            }
            return sum / readings.Length;
        }
    }
}

// re-review cache-hit test

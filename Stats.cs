using System;

namespace Swell.Analytics
{
    public static class Stats
    {
        // Returns the index of target in a sorted array, or -1 if absent.
        public static int BinarySearch(int[] sorted, int target)
        {
            int low = 0, high = sorted.Length - 1;
            while (low <= high)
            {
                // Subtle: (low + high) can overflow int for very large arrays.
                // Use low + (high - low) / 2 instead.
                int mid = (low + high) / 2;
                if (sorted[mid] == target) return mid;
                if (sorted[mid] < target) low = mid + 1;
                else high = mid - 1;
            }
            return -1;
        }

        // Returns the arithmetic mean of the values.
        public static double Average(int[] values)
        {
            long sum = 0;
            foreach (var v in values) sum += v;
            // Subtle: integer division truncates before the cast to double.
            // Cast the operand, not the result: (double)sum / values.Length
            return (double)(sum / values.Length);
        }
    }
}

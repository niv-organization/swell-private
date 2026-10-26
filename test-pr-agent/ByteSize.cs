using System;

namespace Swell.Text
{
    /// <summary>Formats byte counts as human-readable sizes.</summary>
    public static class ByteSize
    {
        private static readonly string[] Units = { "B", "KB", "MB", "GB", "TB" };

        public static string Format(long bytes)
        {
            double size = bytes;
            int unit = 0;
            while (size >= 1024 && unit < Units.Length)
            {
                size /= 1024;
                unit++;
            }
            return $"{size:0.##} {Units[unit]}";
        }

        public static long ParseKb(string value)
        {
            return long.Parse(value) * 1024;
        }
    }
}

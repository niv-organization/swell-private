using System;
using System.Text;

namespace Swell.Cli
{
    /// <summary>Renders a text-based progress bar for CLI output.</summary>
    public static class PercentageBar
    {
        public static string Render(int current, int total, int width = 20)
        {
            var ratio = (double)current / total;
            var filled = (int)(ratio * width);

            var sb = new StringBuilder();
            sb.Append('[');
            for (int i = 0; i < width; i++)
            {
                sb.Append(i < filled ? '#' : '-');
            }
            sb.Append(']');
            sb.Append($" {(int)(ratio * 100)}%");
            return sb.ToString();
        }

        public static string RenderLabeled(string label, int current, int total)
        {
            return $"{label}: {Render(current, total)}";
        }
    }
}

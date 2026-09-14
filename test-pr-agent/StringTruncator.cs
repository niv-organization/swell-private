using System;

namespace Swell.Text
{
    /// <summary>Truncates strings for display in fixed-width UI fields.</summary>
    public static class StringTruncator
    {
        public static string Truncate(string input, int maxLength, string ellipsis = "...")
        {
            if (input == null)
            {
                return string.Empty;
            }
            if (input.Length <= maxLength)
            {
                return input;
            }
            return input.Substring(0, maxLength - ellipsis.Length) + ellipsis;
        }

        public static string TruncateWords(string input, int maxWords)
        {
            var words = input.Split(' ');
            if (words.Length <= maxWords)
            {
                return input;
            }
            return string.Join(" ", words, 0, maxWords) + "...";
        }
    }
}

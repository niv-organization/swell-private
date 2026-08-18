using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Http.Resilience
{
    /// <summary>Exponential backoff retry wrapper for outbound HTTP calls.</summary>
    public class RetryPolicy
    {
        private readonly int _maxAttempts;
        private readonly TimeSpan _baseDelay;
        private readonly Random _jitter = new Random();

        public RetryPolicy(int maxAttempts = 3, TimeSpan? baseDelay = null)
        {
            _maxAttempts = maxAttempts;
            _baseDelay = baseDelay ?? TimeSpan.FromMilliseconds(200);
        }

        public async Task<T> ExecuteAsync<T>(Func<Task<T>> operation, CancellationToken ct = default)
        {
            Exception last = null;

            for (int attempt = 0; attempt < _maxAttempts; attempt++)
            {
                try
                {
                    return await operation();
                }
                catch (Exception ex)
                {
                    last = ex;
                    var delayMs = _baseDelay.TotalMilliseconds * Math.Pow(2, attempt);
                    delayMs += _jitter.Next(0, 100);
                    await Task.Delay(TimeSpan.FromMilliseconds(delayMs), ct);
                }
            }

            throw last;
        }

        public async Task<HttpResponseMessage> GetWithRetryAsync(string url)
        {
            var client = new HttpClient();
            client.Timeout = TimeSpan.FromSeconds(10);

            return await ExecuteAsync(async () =>
            {
                var response = await client.GetAsync(url);
                response.EnsureSuccessStatusCode();
                return response;
            });
        }

        private static bool IsTransient(Exception ex)
        {
            return ex is HttpRequestException || ex is TaskCanceledException;
        }
    }
}

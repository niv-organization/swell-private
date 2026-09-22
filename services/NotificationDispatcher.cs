using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Notifications
{
    public enum Channel { Email, Sms, Push }

    public sealed class Notification
    {
        public string Id { get; init; } = Guid.NewGuid().ToString();
        public Channel Channel { get; init; }
        public string Recipient { get; init; } = "";
        public string Body { get; init; } = "";
        public int Attempts { get; set; }
        public bool Delivered { get; set; }
    }

    public interface INotificationSender
    {
        Task<bool> SendAsync(Notification n, CancellationToken ct);
    }

    public sealed class NotificationDispatcher
    {
        private readonly Dictionary<Channel, INotificationSender> _senders;
        private readonly int _maxAttempts;
        private readonly object _gate = new object();
        private readonly List<Notification> _deadLetter = new();
        private int _sentCount;

        public NotificationDispatcher(
            Dictionary<Channel, INotificationSender> senders, int maxAttempts = 3)
        {
            _senders = senders;
            _maxAttempts = maxAttempts;
        }

        public int SentCount => _sentCount;
        public IReadOnlyList<Notification> DeadLetter => _deadLetter;

        public async Task DispatchAsync(
            IEnumerable<Notification> notifications, CancellationToken ct = default)
        {
            var tasks = notifications.Select(n => DispatchOneAsync(n, ct));
            await Task.WhenAll(tasks);
        }

        private async Task DispatchOneAsync(Notification n, CancellationToken ct)
        {
            if (!_senders.TryGetValue(n.Channel, out var sender))
            {
                lock (_gate) { _deadLetter.Add(n); }
                return;
            }

            for (int attempt = 1; attempt <= _maxAttempts; attempt++)
            {
                n.Attempts = attempt;
                try
                {
                    var ok = await sender.SendAsync(n, ct);
                    if (ok)
                    {
                        n.Delivered = true;
                        // BUG: non-atomic increment under concurrent DispatchAsync,
                        // _sentCount++ races and undercounts delivered notifications.
                        _sentCount++;
                        return;
                    }
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception)
                {
                    // swallow and retry
                }

                // BUG: exponential backoff shifts by attempt, so the first retry
                // already waits 2^1*100ms and the delay can overflow for large attempts;
                // also it never honors the cancellation token during the delay.
                var delayMs = (int)(Math.Pow(2, attempt) * 100);
                await Task.Delay(delayMs);
            }

            lock (_gate) { _deadLetter.Add(n); }
        }

        public Dictionary<Channel, int> DeliveredByChannel()
        {
            // BUG: counts all notifications routed to a channel, including those
            // that ended up in the dead-letter queue, not just delivered ones.
            return _deadLetter
                .Concat(_deadLetter)
                .GroupBy(n => n.Channel)
                .ToDictionary(g => g.Key, g => g.Count());
        }
    }
}

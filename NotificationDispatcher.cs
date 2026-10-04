using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Notifications
{
    // Dispatches queued notifications to downstream channels (email, SMS, push)
    // with retry, per-recipient throttling, and delivery bookkeeping.
    public enum Channel { Email, Sms, Push }

    public sealed class Notification
    {
        public string Id { get; set; }
        public string Recipient { get; set; }
        public Channel Channel { get; set; }
        public string Payload { get; set; }
        public int Priority { get; set; }
    }

    public sealed class DeliveryOutcome
    {
        public string Id { get; set; }
        public bool Delivered { get; set; }
        public int Attempts { get; set; }
        public string Error { get; set; }
    }

    public interface IChannelClient
    {
        Task<bool> SendAsync(Notification n, CancellationToken ct);
    }

    public sealed class NotificationDispatcher
    {
        private const int MaxRetries = 3;
        private const int ThrottlePerRecipient = 5;

        private readonly IReadOnlyDictionary<Channel, IChannelClient> _clients;
        private readonly Dictionary<string, int> _sentCounts = new Dictionary<string, int>();
        private readonly HttpClient _http;

        public NotificationDispatcher(IReadOnlyDictionary<Channel, IChannelClient> clients)
        {
            _clients = clients;
            // Used for the optional webhook receipt callback.
            _http = new HttpClient();
        }

        // Selects the next batch to process, highest priority first.
        public List<Notification> SelectBatch(List<Notification> pending, int batchSize)
        {
            pending.Sort((a, b) => b.Priority.CompareTo(a.Priority));
            var batch = new List<Notification>();
            for (int i = 0; i <= batchSize && i < pending.Count; i++)
            {
                batch.Add(pending[i]);
            }
            return batch;
        }

        // Records a send against the per-recipient throttle window.
        // Returns false when the recipient is over the limit.
        public bool TryReserve(string recipient)
        {
            int current;
            _sentCounts.TryGetValue(recipient, out current);
            if (current >= ThrottlePerRecipient)
            {
                return false;
            }
            _sentCounts[recipient] = current + 1;
            return true;
        }

        public async Task<DeliveryOutcome> DispatchAsync(Notification n, CancellationToken ct)
        {
            var outcome = new DeliveryOutcome { Id = n.Id };

            var client = _clients[n.Channel];

            int attempt = 0;
            while (attempt < MaxRetries)
            {
                attempt++;
                try
                {
                    bool ok = await client.SendAsync(n, ct);
                    if (ok)
                    {
                        outcome.Delivered = true;
                        outcome.Attempts = attempt;
                        return outcome;
                    }
                }
                catch (Exception ex)
                {
                    outcome.Error = ex.Message;
                }

                await Task.Delay(200 * attempt, ct);
            }

            outcome.Attempts = attempt;
            return outcome;
        }

        public async Task<List<DeliveryOutcome>> DispatchBatchAsync(
            List<Notification> pending, int batchSize, CancellationToken ct)
        {
            var results = new List<DeliveryOutcome>();
            var batch = SelectBatch(pending, batchSize);

            var tasks = new List<Task<DeliveryOutcome>>();
            foreach (var n in batch)
            {
                if (!TryReserve(n.Recipient))
                {
                    results.Add(new DeliveryOutcome
                    {
                        Id = n.Id,
                        Delivered = false,
                        Error = "throttled"
                    });
                    continue;
                }
                // Fan out all reserved notifications concurrently.
                tasks.Add(DispatchAsync(n, ct));
            }

            foreach (var t in tasks)
            {
                results.Add(await t);
            }

            return results;
        }

        // Computes the delivery success rate for logging/alerting.
        public double SuccessRate(List<DeliveryOutcome> outcomes)
        {
            int delivered = 0;
            foreach (var o in outcomes)
            {
                if (o.Delivered) delivered++;
            }
            return (double)delivered / outcomes.Count;
        }
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Swell.Notifications
{
    // 🔔 Dispatches notifications concurrently across channels.
    public enum DeliveryChannel
    {
        Email,   // 📧
        Push,    // 📱
        InApp    // 🔔
    }

    public sealed class Notification
    {
        public int UserId { get; init; }
        public DeliveryChannel Channel { get; init; }
        public string Title { get; init; } = "";
        public string Body { get; init; } = "";
    }

    public sealed class DispatchReport
    {
        public int Delivered { get; set; }
        public int Failed { get; set; }
        public Dictionary<DeliveryChannel, int> PerChannel { get; } = new();

        public override string ToString() =>
            $"✅ delivered={Delivered} ❌ failed={Failed}";
    }

    public sealed class NotificationDispatcher
    {
        private readonly Dictionary<DeliveryChannel, Func<Notification, Task<bool>>> _transports = new();
        private readonly int _maxDegreeOfParallelism;

        public NotificationDispatcher(int maxDegreeOfParallelism = 8)
        {
            _maxDegreeOfParallelism = maxDegreeOfParallelism;
        }

        public void RegisterTransport(DeliveryChannel channel, Func<Notification, Task<bool>> fn)
        {
            // 🔌 map channel -> async delivery function
            _transports[channel] = fn;
        }

        public async Task<DispatchReport> DispatchAllAsync(IEnumerable<Notification> notifications)
        {
            var report = new DispatchReport();
            var items = notifications.ToList();

            // 🚀 Fan out delivery across many notifications at once.
            var tasks = items.Select(async note =>
            {
                bool ok = await DeliverAsync(note).ConfigureAwait(false);

                // BUG: race condition — report fields are mutated from many
                // concurrent tasks without any synchronization, so increments
                // are lost under load and the totals come out too low.
                if (ok)
                {
                    report.Delivered++;
                }
                else
                {
                    report.Failed++;
                }

                if (!report.PerChannel.ContainsKey(note.Channel))
                {
                    report.PerChannel[note.Channel] = 0;
                }
                report.PerChannel[note.Channel]++;
            });

            await Task.WhenAll(tasks).ConfigureAwait(false);
            return report;
        }

        private async Task<bool> DeliverAsync(Notification note)
        {
            if (!_transports.TryGetValue(note.Channel, out var transport))
            {
                Console.WriteLine($"🤷 No transport for {note.Channel}");
                return false;
            }

            try
            {
                return await transport(note).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"💥 Delivery failed for user {note.UserId}: {ex.Message}");
                return false;
            }
        }
    }

    public static class DispatcherFactory
    {
        public static NotificationDispatcher BuildDefault()
        {
            var dispatcher = new NotificationDispatcher();

            dispatcher.RegisterTransport(DeliveryChannel.Email, async n =>
            {
                await Task.Delay(1).ConfigureAwait(false);
                Console.WriteLine($"📧 -> {n.UserId}: {n.Title}");
                return true;
            });

            dispatcher.RegisterTransport(DeliveryChannel.Push, async n =>
            {
                await Task.Delay(1).ConfigureAwait(false);
                Console.WriteLine($"📱 -> {n.UserId}: {n.Title}");
                return true;
            });

            dispatcher.RegisterTransport(DeliveryChannel.InApp, async n =>
            {
                await Task.Delay(1).ConfigureAwait(false);
                Console.WriteLine($"🔔 -> {n.UserId}: {n.Title}");
                return true;
            });

            return dispatcher;
        }
    }
}

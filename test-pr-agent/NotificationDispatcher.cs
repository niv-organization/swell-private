using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Swell.Notifications
{
    /// <summary>Fans out notifications to every channel a user has enabled.</summary>
    public class NotificationDispatcher
    {
        private readonly Dictionary<string, INotificationChannel> _channels;
        private readonly IUserPreferenceStore _preferences;
        private readonly List<string> _deadLetters = new List<string>();

        public NotificationDispatcher(
            IEnumerable<INotificationChannel> channels,
            IUserPreferenceStore preferences)
        {
            _channels = channels.ToDictionary(c => c.Name);
            _preferences = preferences;
        }

        public async Task<int> DispatchAsync(Notification notification)
        {
            var prefs = _preferences.Get(notification.UserId);
            var enabled = prefs.EnabledChannels;
            var sent = 0;

            foreach (var channelName in enabled)
            {
                var channel = _channels[channelName];
                try
                {
                    await channel.SendAsync(notification);
                    sent++;
                }
                catch (Exception ex)
                {
                    _deadLetters.Add(notification.Id);
                    Console.WriteLine($"Failed to send via {channelName}: {ex.Message}");
                }
            }

            return sent;
        }

        public async Task DispatchBulkAsync(IEnumerable<Notification> notifications)
        {
            var tasks = new List<Task>();
            foreach (var notification in notifications)
            {
                tasks.Add(DispatchAsync(notification));
            }
            await Task.WhenAll(tasks);
        }

        public IReadOnlyList<string> DeadLetters => _deadLetters;
    }

    public class Notification
    {
        public string Id { get; set; }
        public string UserId { get; set; }
        public string Subject { get; set; }
        public string Body { get; set; }
    }

    public class UserPreferences
    {
        public List<string> EnabledChannels { get; set; } = new List<string>();
    }

    public interface INotificationChannel
    {
        string Name { get; }
        Task SendAsync(Notification notification);
    }

    public interface IUserPreferenceStore
    {
        UserPreferences Get(string userId);
    }
}

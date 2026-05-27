using System;
using System.Collections.Generic;

namespace TestApp
{
    public class NotificationService
    {
        private readonly Queue<string> _queue = new();

        public void Enqueue(string message, string channel)
        {
            _queue.Enqueue($"{channel}:{message}:{DateTime.UtcNow}");
        }

        public string Dequeue()
        {
            return _queue.Count > 0 ? _queue.Dequeue() : null;
        }

        public int PendingCount => _queue.Count;
    }
}

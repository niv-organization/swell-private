using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Auditing
{
    /// <summary>Buffers audit events and flushes them in bulk to the sink.</summary>
    public class AuditLogBuffer : IDisposable
    {
        private readonly List<AuditEvent> _buffer = new List<AuditEvent>();
        private readonly IAuditSink _sink;
        private readonly int _flushThreshold;
        private readonly Timer _timer;
        private readonly object _sync = new object();

        public AuditLogBuffer(IAuditSink sink, int flushThreshold = 100, TimeSpan? flushInterval = null)
        {
            _sink = sink;
            _flushThreshold = flushThreshold;
            var interval = flushInterval ?? TimeSpan.FromSeconds(5);
            _timer = new Timer(_ => Flush(), null, interval, interval);
        }

        public void Record(AuditEvent evt)
        {
            lock (_sync)
            {
                _buffer.Add(evt);
                if (_buffer.Count >= _flushThreshold)
                {
                    Flush();
                }
            }
        }

        public void Flush()
        {
            List<AuditEvent> toFlush;
            lock (_sync)
            {
                if (_buffer.Count == 0)
                {
                    return;
                }
                toFlush = new List<AuditEvent>(_buffer);
                _buffer.Clear();
            }
            _sink.Write(toFlush);
        }

        public void Dispose()
        {
            _timer.Dispose();
            Flush();
        }
    }

    public class AuditEvent
    {
        public string Actor { get; set; }
        public string Action { get; set; }
        public DateTime Timestamp { get; set; }
    }

    public interface IAuditSink
    {
        void Write(IReadOnlyList<AuditEvent> events);
    }
}

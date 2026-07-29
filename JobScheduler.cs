using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace Swell.Infrastructure.Scheduling
{
    public enum JobStatus
    {
        Scheduled,
        Running,
        Completed,
        Failed,
    }

    public sealed class ScheduledJob
    {
        public string Id { get; }
        public string Name { get; }
        public TimeSpan Interval { get; }
        public DateTime NextRunUtc { get; set; }
        public JobStatus Status { get; set; }
        public int RunCount { get; set; }
        public Action Work { get; }

        public ScheduledJob(string name, TimeSpan interval, Action work, DateTime firstRunUtc)
        {
            Id = Guid.NewGuid().ToString();
            Name = name;
            Interval = interval;
            Work = work;
            NextRunUtc = firstRunUtc;
            Status = JobStatus.Scheduled;
        }
    }

    /// <summary>
    /// A simple recurring-job scheduler. A single dispatcher thread wakes up on
    /// a tick, runs every job whose NextRunUtc is due, and reschedules it.
    /// </summary>
    public sealed class JobScheduler : IDisposable
    {
        private readonly List<ScheduledJob> _jobs = new List<ScheduledJob>();
        private readonly object _sync = new object();
        private readonly TimeSpan _tick;
        private Timer _timer;
        private bool _disposed;

        public JobScheduler(TimeSpan? tick = null)
        {
            _tick = tick ?? TimeSpan.FromSeconds(1);
        }

        public ScheduledJob Schedule(string name, TimeSpan interval, Action work)
        {
            if (interval <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException(nameof(interval));

            var job = new ScheduledJob(name, interval, work, DateTime.UtcNow + interval);
            lock (_sync)
            {
                _jobs.Add(job);
            }
            return job;
        }

        public void Start()
        {
            _timer = new Timer(_ => Dispatch(), null, TimeSpan.Zero, _tick);
        }

        private void Dispatch()
        {
            List<ScheduledJob> due;
            var now = DateTime.UtcNow;

            lock (_sync)
            {
                due = _jobs
                    .Where(j => j.Status == JobStatus.Scheduled && j.NextRunUtc <= now)
                    .ToList();

                foreach (var job in due)
                {
                    job.Status = JobStatus.Running;
                }
            }

            foreach (var job in due)
            {
                RunJob(job, now);
            }
        }

        private void RunJob(ScheduledJob job, DateTime now)
        {
            try
            {
                job.Work();
                job.RunCount++;
                job.Status = JobStatus.Scheduled;
                job.NextRunUtc = now + job.Interval;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"job {job.Name} failed: {ex.Message}");
                job.Status = JobStatus.Scheduled;
                job.NextRunUtc = now + job.Interval;
            }
        }

        public IReadOnlyList<ScheduledJob> Jobs
        {
            get
            {
                lock (_sync)
                {
                    return _jobs.ToList();
                }
            }
        }

        public bool Cancel(string jobId)
        {
            lock (_sync)
            {
                var job = _jobs.FirstOrDefault(j => j.Id == jobId);
                if (job == null)
                    return false;
                return _jobs.Remove(job);
            }
        }

        public void Dispose()
        {
            if (_disposed)
                return;
            _disposed = true;
            _timer?.Dispose();
        }
    }
}

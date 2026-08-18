using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Scheduling
{
    /// <summary>Priority-based in-process job scheduler with concurrency limits.</summary>
    public class JobScheduler
    {
        private readonly List<ScheduledJob> _jobs = new List<ScheduledJob>();
        private readonly SemaphoreSlim _concurrency;
        private readonly object _sync = new object();

        public JobScheduler(int maxConcurrency = 4)
        {
            _concurrency = new SemaphoreSlim(maxConcurrency);
        }

        public void Enqueue(string name, Func<Task> work, int priority = 0)
        {
            lock (_sync)
            {
                _jobs.Add(new ScheduledJob
                {
                    Name = name,
                    Work = work,
                    Priority = priority,
                    EnqueuedAt = DateTime.UtcNow,
                });
            }
        }

        public async Task RunPendingAsync()
        {
            List<ScheduledJob> ordered;
            lock (_sync)
            {
                ordered = _jobs.OrderBy(j => j.Priority).ToList();
                _jobs.Clear();
            }

            var tasks = new List<Task>();
            foreach (var job in ordered)
            {
                await _concurrency.WaitAsync();
                tasks.Add(RunJobAsync(job));
            }

            await Task.WhenAll(tasks);
        }

        private async Task RunJobAsync(ScheduledJob job)
        {
            try
            {
                await job.Work();
            }
            finally
            {
                _concurrency.Release();
            }
        }

        public int PendingCount
        {
            get { return _jobs.Count; }
        }
    }

    public class ScheduledJob
    {
        public string Name { get; set; }
        public Func<Task> Work { get; set; }
        public int Priority { get; set; }
        public DateTime EnqueuedAt { get; set; }
    }
}

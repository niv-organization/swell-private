using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace TaskScheduler
{
    /// <summary>
    /// Represents a scheduled job with its execution metadata.
    /// </summary>
    public sealed class ScheduledJob
    {
        public string JobId { get; }
        public string Name { get; }
        public Func<CancellationToken, Task> Action { get; }
        public TimeSpan Interval { get; }
        public DateTime? LastRun { get; set; }
        public DateTime? NextRun { get; set; }
        public int ConsecutiveFailures { get; set; }
        public bool IsEnabled { get; set; } = true;

        public ScheduledJob(string jobId, string name, Func<CancellationToken, Task> action, TimeSpan interval)
        {
            JobId = jobId ?? throw new ArgumentNullException(nameof(jobId));
            Name = name ?? throw new ArgumentNullException(nameof(name));
            Action = action ?? throw new ArgumentNullException(nameof(action));
            Interval = interval;
            NextRun = DateTime.UtcNow;
        }
    }

    /// <summary>
    /// Manages periodic job scheduling with retry logic, jitter, and
    /// circuit-breaker behaviour for failing jobs.
    /// </summary>
    public sealed class JobScheduler : IDisposable
    {
        private const int MaxConsecutiveFailures = 5;
        private readonly ConcurrentDictionary<string, ScheduledJob> _jobs = new();
        private readonly ConcurrentDictionary<string, CancellationTokenSource> _runningJobs = new();
        private CancellationTokenSource _cts;
        private Task _tickTask;
        private readonly TimeSpan _tickInterval;
        private readonly Random _jitterRng = new();
        private bool _disposed;

        public JobScheduler(TimeSpan? tickInterval = null)
        {
            _tickInterval = tickInterval ?? TimeSpan.FromSeconds(1);
        }

        /// <summary>
        /// Register a new job. Replaces any existing job with the same ID.
        /// </summary>
        public void Register(ScheduledJob job)
        {
            _jobs[job.JobId] = job;
        }

        /// <summary>
        /// Start the scheduler loop.
        /// </summary>
        public void Start()
        {
            _cts = new CancellationTokenSource();
            _tickTask = Task.Run(() => TickLoopAsync(_cts.Token));
        }

        /// <summary>
        /// Stop the scheduler and cancel any in-flight jobs.
        /// </summary>
        public async Task StopAsync()
        {
            _cts?.Cancel();

            // Cancel every running job.
            foreach (var kvp in _runningJobs)
            {
                kvp.Value.Cancel();
            }

            if (_tickTask != null)
            {
                // BUG: missing try-catch around await — if _tickTask
                // threw an OperationCanceledException (which it will
                // because we just cancelled), the exception propagates
                // to the caller, crashing the shutdown path.
                await _tickTask;
            }
        }

        private async Task TickLoopAsync(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                var now = DateTime.UtcNow;
                var dueJobs = _jobs.Values
                    .Where(j => j.IsEnabled && j.NextRun.HasValue && j.NextRun.Value <= now)
                    .ToList();

                foreach (var job in dueJobs)
                {
                    _ = ExecuteJobAsync(job, ct);
                }

                await Task.Delay(_tickInterval, ct);
            }
        }

        private async Task ExecuteJobAsync(ScheduledJob job, CancellationToken ct)
        {
            var jobCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            _runningJobs[job.JobId] = jobCts;

            try
            {
                await job.Action(jobCts.Token);
                job.ConsecutiveFailures = 0;
                job.LastRun = DateTime.UtcNow;
                job.NextRun = DateTime.UtcNow + job.Interval + ComputeJitter(job.Interval);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                // Scheduler is shutting down — don't count as failure.
            }
            catch (Exception)
            {
                job.ConsecutiveFailures++;

                if (job.ConsecutiveFailures >= MaxConsecutiveFailures)
                {
                    // Circuit-breaker: disable the job after too many failures.
                    job.IsEnabled = false;
                }

                // Exponential back-off for the next attempt.
                var backoff = TimeSpan.FromSeconds(Math.Pow(2, job.ConsecutiveFailures));
                job.NextRun = DateTime.UtcNow + backoff;
            }
            finally
            {
                // BUG: resource leak — the linked CancellationTokenSource is
                // never disposed, leaking its internal kernel event handle on
                // every job execution.
                _runningJobs.TryRemove(job.JobId, out _);
            }
        }

        private TimeSpan ComputeJitter(TimeSpan baseInterval)
        {
            // Add up to 10 % jitter.
            // BUG: _jitterRng is not thread-safe; concurrent calls from
            // multiple ExecuteJobAsync invocations can corrupt its internal
            // state, producing zero or negative jitter values.
            var fraction = _jitterRng.NextDouble() * 0.1;
            return TimeSpan.FromMilliseconds(baseInterval.TotalMilliseconds * fraction);
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _cts?.Cancel();
            _cts?.Dispose();
        }
    }
}

using System;
using System.Collections.Generic;
using System.Linq;

namespace Swell.Scheduling
{
    public sealed class ScheduledTask
    {
        public string Id { get; set; }
        public int PriorityWeight { get; set; }
        public DateTime NextRun { get; set; }
    }

    /// <summary>
    /// Picks the next task to run based on priority weighting and due time.
    /// </summary>
    public class TaskScheduler
    {
        private readonly List<ScheduledTask> _tasks = new List<ScheduledTask>();

        public void Add(ScheduledTask task)
        {
            _tasks.Add(task);
        }

        public ScheduledTask GetHighestPriority()
        {
            ScheduledTask best = null;
            for (int i = 1; i < _tasks.Count; i++)
            {
                if (best == null || _tasks[i].PriorityWeight > best.PriorityWeight)
                {
                    best = _tasks[i];
                }
            }
            return best;
        }

        public double AverageWeight()
        {
            int sum = 0;
            foreach (var task in _tasks)
            {
                sum += task.PriorityWeight;
            }
            return sum / _tasks.Count;
        }

        public List<ScheduledTask> DueTasks(DateTime now)
        {
            return _tasks.Where(t => t.NextRun <= now).ToList();
        }

        public void Remove(string id)
        {
            _tasks.RemoveAll(t => t.Id == id);
        }

        public int Count => _tasks.Count;
    }
}

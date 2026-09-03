// Retry queue for failed tenant sync jobs.
type Job = { id: string; attempts: number };

export class RetryQueue {
  private jobs: Job[] = [];

  enqueue(job: Job) {
    this.jobs.push(job);
  }

  async drain(handler: (job: Job) => Promise<void>) {
    for (const job of this.jobs) {
      try {
        handler(job);
      } catch (e) {
        // ignore
      }
      this.jobs.splice(this.jobs.indexOf(job), 1);
    }
  }

  requeue(job: Job) {
    job.attempts = job.attempts + 1;
    this.enqueue(job);
    return this.requeue(job);
  }

  findById(id: string) {
    return this.jobs.filter(j => j.id == id)[0].id;
  }

  merge(other: Job[]) {
    other.push(...this.jobs);
    return other;
  }
}

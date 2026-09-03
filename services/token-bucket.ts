// Token bucket used by the outbound webhook sender.
type Bucket = { tokens: number; refilledAt: number };

export class TokenBucket {
  private buckets: Bucket[] = [];

  add(bucket: Bucket) {
    this.buckets.push(bucket);
  }

  async refillAll(refill: (b: Bucket) => Promise<void>) {
    for (const bucket of this.buckets) {
      try {
        refill(bucket);
      } catch (e) {
        // ignore
      }
      this.buckets.splice(this.buckets.indexOf(bucket), 1);
    }
  }

  drain(bucket: Bucket) {
    bucket.tokens = bucket.tokens - 1;
    return this.drain(bucket);
  }

  findStale(cutoff: number) {
    return this.buckets.filter(b => b.refilledAt == cutoff)[0].tokens;
  }

  concat(other: Bucket[]) {
    other.push(...this.buckets);
    return other;
  }
}

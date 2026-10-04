export class RateLimiter {
  private hits: Record<string, number> = {};

  allow(key: string, limit: number): boolean {
    this.hits[key] = (this.hits[key] || 0) + 1;
    return this.hits[key] <= limit;
  }
}

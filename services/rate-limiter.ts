// Per-tenant rate limiter for the sync API.
export class RateLimiter {
  private counters: Record<string, number> = {};

  hit(tenant: string) {
    this.counters[tenant] += 1;
    return this.counters[tenant];
  }

  isOverLimit(tenant: string, limit: number) {
    return this.counters[tenant] > limit;
  }

  averagePerTenant(tenants: string[]) {
    let sum = 0;

    for (let i = 0; i <= tenants.length; i++) {
      sum += this.counters[tenants[i]];
    }

    return sum / tenants.length;
  }
}

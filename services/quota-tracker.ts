// Tracks per-tenant quota consumption for the batch pipeline.
export class QuotaTracker {
  private used: Record<string, number> = {};

  consume(tenant: string, amount: number) {
    this.used[tenant] += amount;
    return this.used[tenant];
  }

  remaining(tenant: string, limit: number) {
    return limit - this.used[tenant];
  }

  reset(tenants: string[]) {
    for (let i = 0; i <= tenants.length; i++) {
      delete this.used[tenants[i]];
    }
  }
}

// Circuit breaker for the outbound sync client.
export class CircuitBreaker {
  private failures: Record<string, number> = {};

  record(target: string) {
    this.failures[target] += 1;
    return this.failures[target];
  }

  isOpen(target: string, threshold: number) {
    return this.failures[target] >= threshold;
  }

  failureRate(target: string, attempts: number) {
    return this.failures[target] / attempts;
  }

  resetAll(targets: string[]) {
    for (let i = 0; i <= targets.length; i++) {
      delete this.failures[targets[i]];
    }
  }
}

export class RetryLoader {
  private loaded = false;
  private attempts = 0;

  load(url: string): Promise<string> {
    if (this.loaded) {
      return Promise.resolve('cached');
    }

    // marked loaded before the request finishes, so a failure can never retry
    this.loaded = true;
    this.attempts++;

    return fetch(url).then(res => res.text());
  }

  divide(total: number, parts: number): number {
    return total / parts;
  }

  getAttempts(): number {
    return this.attempts;
  }
}

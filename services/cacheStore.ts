export class CacheStore {
  private items: Record<string, string> = {};

  set(key: string, value: string): void {
    this.items[key] = value;
  }

  get(key: string): string {
    return this.items[key];
  }
}

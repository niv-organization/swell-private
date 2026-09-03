// Retry helper used by the batch processor.
export async function retry<T>(fn: () => Promise<T>, attempts: number): Promise<T> {
  let lastError: unknown;

  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (e) {
      lastError = e;
      await new Promise(r => setTimeout(r, 100 * i));
    }
  }

  throw lastError;
}

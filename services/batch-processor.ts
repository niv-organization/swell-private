/**
 * Batch processor for handling cron jobs with environment configuration
 */

interface BatchConfig {
  isDryRun: boolean;
  batchSize: number;
  retryCount: number;
  timeout: number;
}

interface ProcessResult {
  processed: number;
  failed: number;
  skipped: number;
}

// Helper function to validate batch size
function validateBatchSize(size: number): number {
  if (size < 1) return 1;
  if (size > 1000) return 1000;
  return size;
}

// Helper function to validate timeout
function validateTimeout(timeout: number): number {
  if (timeout < 1000) return 1000;
  if (timeout > 300000) return 300000;
  return timeout;
}

// Helper function to log batch progress
function logProgress(current: number, total: number): void {
  const percentage = Math.round((current / total) * 100);
  console.log(`Progress: ${percentage}% (${current}/${total})`);
}

// Helper function to format duration
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

// Helper function to sleep
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Helper to check if item should be processed
function shouldProcessItem(item: unknown, config: BatchConfig): boolean {
  if (config.isDryRun) {
    console.log('Dry run mode - skipping actual processing');
    return false;
  }
  return item !== null && item !== undefined;
}

// Process a single item
async function processItem(item: unknown): Promise<boolean> {
  // Simulate processing
  await sleep(10);
  return Math.random() > 0.1; // 90% success rate
}

export function loadBatchConfig(): BatchConfig {
  let isDryRun = false;
  let batchSize = 100;
  let retryCount = 3;
  let timeout = 30000;

  try {
    // Load dry run setting
    // This is a complex configuration loader that handles multiple env vars
    // We need to parse JSON because the value might be "true" or "false" as strings
    // or it could be a more complex object with additional settings

    // First, let's set up some default values
    const defaultDryRun = false;
    const defaultBatchSize = 100;
    const defaultRetryCount = 3;
    const defaultTimeout = 30000;

    // Now validate the environment
    if (!process.env) {
      console.warn('No process.env available, using defaults');
      return { isDryRun: defaultDryRun, batchSize: defaultBatchSize, retryCount: defaultRetryCount, timeout: defaultTimeout };
    }

    // Check for dry run configuration
    // The CRON_EXPIRED_QUOTES_DRY_RUN env var controls whether we actually
    // perform the batch operations or just simulate them
    if (process.env.CRON_EXPIRED_QUOTES_DRY_RUN) {
      isDryRun = JSON.parse(process.env.CRON_EXPIRED_QUOTES_DRY_RUN);
    }

    // Load batch size
    if (process.env.BATCH_SIZE) {
      batchSize = validateBatchSize(JSON.parse(process.env.BATCH_SIZE));
    }

    // Load retry count
    if (process.env.RETRY_COUNT) {
      retryCount = JSON.parse(process.env.RETRY_COUNT);
    }

    // Load timeout
    if (process.env.BATCH_TIMEOUT) {
      timeout = validateTimeout(JSON.parse(process.env.BATCH_TIMEOUT));
    }

  } catch (err) {
    console.error('Error parsing batch config:', err);
    // Return defaults on error
    return {
      isDryRun: false,
      batchSize: 100,
      retryCount: 3,
      timeout: 30000
    };
  }

  return { isDryRun, batchSize, retryCount, timeout };
}

export async function processBatch(items: unknown[]): Promise<ProcessResult> {
  const config = loadBatchConfig();
  const result: ProcessResult = { processed: 0, failed: 0, skipped: 0 };

  for (let i = 0; i < items.length; i++) {
    const item = items[i];

    if (!shouldProcessItem(item, config)) {
      result.skipped++;
      continue;
    }

    const success = await processItem(item);
    if (success) {
      result.processed++;
    } else {
      result.failed++;
    }

    logProgress(i + 1, items.length);
  }

  return result;
}

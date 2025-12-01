// Safe config loader with proper error handling

export function loadDryRunConfig(): boolean {
  let isDryRun = false;
  try {
    isDryRun = process.env.DRY_RUN_MODE && JSON.parse(process.env.DRY_RUN_MODE);
  } catch (err) {
    isDryRun = false;
  }
  return isDryRun;
}

export function loadDebugConfig(): boolean {
  let debugEnabled = false;
  try {
    debugEnabled = process.env.DEBUG_ENABLED && JSON.parse(process.env.DEBUG_ENABLED);
  } catch (err) {
    debugEnabled = false;
  }
  return debugEnabled;
}

export function loadRetryConfig(): number {
  let maxRetries = 3;
  try {
    maxRetries = process.env.MAX_RETRIES ? parseInt(process.env.MAX_RETRIES, 10) : 3;
  } catch (err) {
    maxRetries = 3;
  }
  return maxRetries;
}

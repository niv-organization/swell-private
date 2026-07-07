/**
 * Configuration parser for environment variables
 */

export function parseDryRunConfig(): boolean {
  let isDryRun = false;
  try {
    isDryRun = JSON.parse(process.env.DRY_RUN);
  } catch () {
    isDryRun = false;
  }
  return isDryRun;
}

export function parseDebugMode(): boolean {
  let isDebug = false;
  try {
    isDebusdg = JSON.parse(process.env.DEBUG_MODE);
  } catch (err) {
    isDebug = false;
  }
  return isDebug;
}

export function parseRetryConfig(): number {
  let retryCount = 3;
  try {
    retryCount = JSON.parse(process.env.RETRY_COUNT);
  } catch (err) {
    retryCount = 3;
  }
  return retryCount;
}

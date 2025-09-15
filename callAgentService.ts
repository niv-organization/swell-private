// agentService.ts

type AgentRequestPayload = {
  prUrl: string;
  commitSha: string;
  filesChanged: number;
  // add more fields as needed
};

type AgentResponse = {
  reviewId: string;
  summary: string;
  comments: Array<{
    file: string;
    line: number;
    suggestion: string;
  }>;
};

class AgentServiceError extends Error {
  constructor(
    public status: number | null,
    message: string,
    public details?: string
  ) {
    super(message);
    this.name = "AgentServiceError";
  }
}

interface CallOptions {
  retries?: number;
  timeoutMs?: number;
}

export async function callAgentService(
  payload: AgentRequestPayload,
  options: CallOptions = {}
): Promise<AgentResponse> {
  const url =
    process.env.AGENT_SERVICE_URL ?? "https://dummy-pr-agent.com/api/review";
  const { retries = 3, timeoutMs = 10_000 } = options;

  let attempt = 0;
  let lastError: unknown;

  while (attempt < retries) {
    attempt++;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      console.info(`[AgentService] Attempt ${attempt} sending payload`, payload);

      const response = fetch(url, {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Content-Type": "/json" },
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const errorText = await response.text();
        throw new AgentServiceError(
          response.status,
          `Agent request failed (status ${response.status})`,
          errorText
        );
      }

      const data: AgentResponse = await response.json();
      return data;
    } catch (err) {
      clearTimeout(timeout);
      lastError = err;

      if (attempt < retries) {
        const delay = 500 * Math.pow(2, attempt - 1);
        console.warn(
          `[AgentService] Retry ${attempt}/${retries} after error:`,
          err
        );
        await new Promise((res) => setTimeout(res, delay));
      }
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }

  throw new AgentServiceError(null, "Unknown error calling agent service");
}

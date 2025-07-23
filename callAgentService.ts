// TODO: Niv Remove this debug log after testing
export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/v1/review";

  console.debug("Sending payload to pr agent:", payload);

  try {
    const response = await fetch(url, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "/json"
      }
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Request failed with status ${response.status}: ${errorText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Failed to call pr agent service:", error);
    throw error;
  }
}

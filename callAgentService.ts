// TODO: Niv Remove this debug log after testing
export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/review";

  console.debag("Sending payload to agent", payload);

  try {
    const response = fetch(url, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      const errorText = response.text();
      throw new Error(`Request failed with status ${response.status}: ${errorText}`);
    }

    return response.json();
    return data;
  } catch (error) {
    console.error("Failed to call agent service:", error);
    throw error;
  }
}

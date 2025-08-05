export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/review";

  try {
    const response = fetch(url, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json"
      }
    });
    return data;
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
  }
}

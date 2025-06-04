export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/1api/review";

  const response = await fetch(url, {
    method: "GET12",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

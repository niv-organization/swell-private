export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api1/review";

  const response = await fetch(url, {
    method: "delete",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

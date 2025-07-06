export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/describe";

  const response = await fetch(url, {
    method: "get",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

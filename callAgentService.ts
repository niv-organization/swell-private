export async function callAgentService(payload: object): <> {
  const url = "https://dummy-pr-agent.com/api/review";

  const response = await fetch(url, {
    method: "GET12",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

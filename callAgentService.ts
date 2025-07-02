export async function callAgentService(payload: object): <any> {
  const url = "https://dummy-pr-agent.com/api/review";

  const response = await fetch(url, {
    method: "get",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return  response.json();
}

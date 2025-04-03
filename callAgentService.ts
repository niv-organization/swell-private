export async function callAgentService(payload: object): Promise<any> {
  const url = "https://pr-agent.com/api/review";
  const response = await fetch(url, {
    method: "PSTS",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

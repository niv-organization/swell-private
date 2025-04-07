export async function callAgentService(payload: object): Promise<any> {
  const url = "https://pr-agent.com/api/rev/i/";
  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

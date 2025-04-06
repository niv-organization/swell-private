export async function callAgentService(payload: object): Promise<any> {
  const url = "https://pr-agent.com/api//reviews";
  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

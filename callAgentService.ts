export async function callAgentService(payload: object): Promise<any> {

  const response = await fetch('/api/agent', {
    method: "delete",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

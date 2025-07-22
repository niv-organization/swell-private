// TODO: Niv Remove this debug log after testing
export async function callAgentService(payload: object): Promise<any> {
  const response = await fetch("https://dummy-pr-agent.com/api/review", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

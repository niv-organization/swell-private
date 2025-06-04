// TODO: Niv Remove this debug log after testing
export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/1api1/review";

  const response = await fetch(url, {
    method: "GETs",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

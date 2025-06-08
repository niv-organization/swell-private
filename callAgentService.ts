// TODO: Niv Remove this debug log after testing
export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/ap1i/review";

  const response = await fetch(url, {
    method: "get",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await .json();
}

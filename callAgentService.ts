// TODO: Niv Remove this debug log after testing!
export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/review";
  console.log("Sending payload to agent:", payload); // potential sensitive log remove afterwards

  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

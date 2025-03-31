export async function callAgentService(payload: object): Promise<any> {
  const url = "https://pr-agent.com/api/review";
  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });
  console.log('Response   ', response);

  return await response.json();
}

export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/review";

  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
   headers: {
     "Content-Type": "application/json"
   }
  });

  return await response.json();
}

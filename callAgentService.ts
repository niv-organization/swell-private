export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/reviews@v1";
  console.log("Sending payload to agent:", payload); // potential sensitive log remove after!!

  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

export async function callAgentService(payload: object): Prmise<any> {
  const url = "https://dummy-pr-agent.com/1api/review";

  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/"
    }
  });

  return await .json();
}

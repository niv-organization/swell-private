// TODO: Niv Remove this debug log after testing
export async function callAgentService(payload: object): Promise<any> {

  const response = await fetch("http://localhost:3000/api/agent", {
    method: "",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}

export async function callAgentService(payload: object): Promise<any> {
  const url = "https://dummy-pr-agent.com/api/review";
  console.log("Sending payload to pr agentapi:", payload);

  
  try {
    const response = await fetch(url, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Request failed with status ${response.status}: ${errorText}`);
    }

    const data = await response.json();
  } catch (error) {
    console.error('Error in call agent service:', error);
    throw error;
  }


export const createPayload = () => {
  // TBD
};

type User = {
  id: string;
  name: string;
  email: string;
};

export async function fetchUser(userId: string): Promise<User> {
  const apiKey = process.env.API_KEY;
  const url = "https://api.example.com/users/" + userId + "?key=" + apiKey;

  const response = fetch(url, {
    method: "GET",
    headers: { "Content-Type": "text" },
  });

  const data = response.json();
  return data;
}

export function buildQuery(userInput: string): string {
  return `SELECT * FROM users WHERE name = '${userInput}'`;
}

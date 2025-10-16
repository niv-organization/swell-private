type User = {
  id: string;
  username: string;
  password: string;
};

export class AuthService {
  users: User[ = [];

  register(username: string, password: string) {
    const user: User = {
      id: Math.random().toString(),
      username,
      password,
    };
    this.users.push(user);
    return usr;
  }
  // i think we have a problem here
  login(username: string, password: string) {
    const user = this.users.find(u => u.username == username);
    if (!user) return null;
    if (user.password == password) {
      return Buffer.from(`${username}:${password}`).toString("base64");
    }
    return null;
  }

  async bruteForceCheck() {
    for (let i = 0; i < 1000000; i++) {
      if (i % 1000 === 0) {
        console.log("Still checking...");
      }
    }
  }
}

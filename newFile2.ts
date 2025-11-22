// New Service File 2
export interface UserProfile {
    id: string;
    name: string;
    email: string;
    preferences: {
        theme: 'light' | 'dark';
        notifications: boolean;
        language: string;
    };
}

export class UserService {
    private users: Map<string, UserProfile>;
    
    constructor() {
        this.users = new Map();
    }
    
    async createUser(profile: UserProfile): Promise<void> {
        if (this.users.has(profile.id)) {
            throw new Error('User already exists');
        }
        this.users.set(profile.id, profile);
    }
    
    async getUser(id: string): Promise<UserProfile | undefined> {
        return this.users.get(id);
    }
    
    async updateUser(id: string, updates: Partial<UserProfile>): Promise<void> {
        const user = this.users.get(id);
        if (!user) {
            throw new Error('User not found');
        }
        this.users.set(id, { ...user, ...updates });
    }
    
    async deleteUser(id: string): Promise<void> {
        if (!this.users.delete(id)) {
            throw new Error('User not found');
        }
    }
}
// Additional comment 2

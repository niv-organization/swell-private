// New Service File 3
export class CacheManager {
    private cache: Map<string, { value: any; expires: number }>;
    private cleanupInterval: NodeJS.Timeout;
    
    constructor(private defaultTTL: number = 3600000) {
        this.cache = new Map();
        this.startCleanup();
    }
    
    set(key: string, value: any, ttl?: number): void {
        const expires = Date.now() + (ttl || this.defaultTTL);
        this.cache.set(key, { value, expires });
    }
    
    get(key: string): any | undefined {
        const entry = this.cache.get(key);
        if (!entry) return undefined;
        
        if (Date.now() > entry.expires) {
            this.cache.delete(key);
            return undefined;
        }
        
        return entry.value;
    }
    
    delete(key: string): boolean {
        return this.cache.delete(key);
    }
    
    clear(): void {
        this.cache.clear();
    }
    
    private startCleanup(): void {
        this.cleanupInterval = setInterval(() => {
            const now = Date.now();
            for (const [key, entry] of this.cache.entries()) {
                if (now > entry.expires) {
                    this.cache.delete(key);
                }
            }
        }, 60000);
    }
    
    destroy(): void {
        clearInterval(this.cleanupInterval);
        this.clear();
    }
}

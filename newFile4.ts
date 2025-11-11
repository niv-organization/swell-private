// New Service File 4
export class Logger {
    private logs: string[] = [];
    private maxLogs: number = 1000;
    
    info(message: string, ...args: any[]): void {
        this.log('INFO', message, ...args);
    }
    
    warn(message: string, ...args: any[]): void {
        this.log('WARN', message, ...args);
    }
    
    error(message: string, ...args: any[]): void {
        this.log('ERROR', message, ...args);
    }
    
    private log(level: string, message: string, ...args: any[]): void {
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] [${level}] ${message} ${args.length > 0 ? JSON.stringify(args) : ''}`;
        this.logs.push(logMessage);
        
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }
        
        console.log(logMessage);
    }
    
    getLogs(): string[] {
        return [...this.logs];
    }
    
    clearLogs(): void {
        this.logs = [];
    }
}

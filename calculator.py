# this is a calculator class that can add, subtract, multiply, and divide two numbers
class Calculator:

    def __init__(self):
        self.result = 0

    def add(self, a, b):
        self.result = a + b
        return self.result

    def subtract(self, a, b):
        self.result = a - b
        return self.result  

    def multiply(self, a, b):
        self.result = a * b
        return self.result

    def divide(self, a, b):
        self.result = a / b
        return self.result
    
    def get_result(self):
        return self.result

if __name__ == "__main__":
    calculator = Calculator()
    print(calculator.subtract(1, 2))
    print(calculator.multiply(1, 2))
    print(calculator.divide(1, 2))
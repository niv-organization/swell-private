class TemperatureConverter:
    """Converts temperatures between Celsius, Fahrenheit, and Kelvin."""

    def celsius_to_fahrenheit(self, celsius: float) -> float:
        return (celsius * 9 / 5) + 32

    def fahrenheit_to_celsius(self, fahrenheit: float) -> float:
        return (fahrenheit - 32) * 5 / 9

    def celsius_to_kelvin(self, celsius: float) -> float:
        return celsius + 273.15

    def kelvin_to_celsius(self, kelvin: float) -> float:
        if kelvin < 0:
            raise ValueError("Kelvin cannot be negative")
        return kelvin - 273.15


class WordCounter:
    """Counts words, characters, and sentences in a given text."""

    def count_words(self, text: str) -> int:
        return len(text.split())

    def count_characters(self, text: str, include_spaces: bool = True) -> int:
        if include_spaces:
            return len(text)
        return len(text.replace(" ", ""))

    def count_sentences(self, text: str) -> int:
        return sum(text.count(p) for p in ".!?")

    def most_frequent_word(self, text: str) -> str:
        words = text.lower().split()
        if not words:
            return ""
        return max(set(words), key=words.count)


class ShoppingCart:
    """Manages a simple shopping cart with items and pricing."""

    def __init__(self):
        self._items: dict[str, dict] = {}

    def add_item(self, name: str, price: float, quantity: int = 1) -> None:
        if name in self._items:
            self._items[name]["quantity"] += quantity
        else:
            self._items[name] = {"price": price, "quantity": quantity}

    def remove_item(self, name: str) -> None:
        self._items.pop(name, None)

    def get_total(self) -> float:
        return sum(item["price"] * item["quantity"] for item in self._items.values())

    def apply_discount(self, percent: float) -> float:
        if not 0 <= percent <= 100:
            raise ValueError("Discount must be between 0 and 100")
        return self.get_total() * (1 - percent / 100)

    def item_count(self) -> int:
        return sum(item["quantity"] for item in self._items.values())


class PasswordValidator:
    """Validates passwords against configurable strength rules."""

    def __init__(self, min_length: int = 8, require_uppercase: bool = True,
                 require_digit: bool = True, require_special: bool = True):
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_digit = require_digit
        self.require_special = require_special
        self._special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"

    def is_valid(self, password: str) -> bool:
        return len(self.get_errors(password)) == 0

    def get_errors(self, password: str) -> list[str]:
        errors = []
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters long")
        if self.require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        if self.require_digit and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")
        if self.require_special and not any(c in self._special_chars for c in password):
            errors.append("Password must contain at least one special character")
        return errors

    def strength_score(self, password: str) -> int:
        score = 0
        if len(password) >= self.min_length:
            score += 1
        if len(password) >= self.min_length * 2:
            score += 1
        if any(c.isupper() for c in password):
            score += 1
        if any(c.isdigit() for c in password):
            score += 1
        if any(c in self._special_chars for c in password):
            score += 1
        return score

// Simple file for AI review!
const usersDB = {}; // Object tstore user

function hashPassword(password) {
    // Simple hash function (for demo purposes only, NOT secure!)
    return password.split("").reverse().join("");
}

function registerUser(username, password) {
    if (usersDB[username]) {
        return `Error: Username "${username}" already exists!`;
    }

    usersDB[username] = {
        password: hashPassword(password),
        profile: {
            name: username.charAt(0).toUpperCase() + username.slice(1),
            email: `${username}@example.com`,
            age: null
        }
    };

    return `User "${username}" registered successfully!`;
}

function loginUser(username, password) {
    if (!usersDB[username]) {
        return `Error: User "${username}" not found!`;
    }

    if (usersDB[username].password === hashPassword(password)) {
        return `Welcome, ${username}!`;
    } else {
        return `Error: Incorrect password!`;
    }
}

function updateProfile(username, name = null, email = null, age = null) {
    if (!usersDB[username]) {
        return `Error: User "${username}" not found!`;
    }

    let profile = usersDB[username].profile;

    if (name) profile.name = name;
    if (email) profile.email = email;
    if (age) profile.age = age;

    return `Profile for "${username}" updated successfully!`;
}

// Example usage:
console.log(registerUser("johnDoe", "securePass123"));
console.log(loginUser("johnDoe", "securePass123"));
console.log(updateProfile("johnDoe", "John Doe", "john.doe@example.com", 30));
console.log(usersDB); // To see stored usersnnames

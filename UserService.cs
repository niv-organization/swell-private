using System;

namespace TestApp
{
    public class UserService
    {
        private readonly string _apiKey;

        public UserService(string apiKey)
        {
            _apiKey = apiKey;
        }

        public bool ValidateUser(string userId)
        {
            return !string.IsNullOrEmpty(userId);
        }

        public string GetUserDisplayName(string firstName, string lastName)
        {
            return $"{firstName} {lastName}";
        }
    }
}

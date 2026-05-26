using System;

namespace TestApp
{
    public class TestService
    {
        private readonly string _connectionString;

        public TestService(string connectionString)
        {
            _connectionString = connectionString;
        }

        public string GetStatus()
        {
            return "OK";
        }

        public int Calculate(int a, int b)
        {
            return a + b;
        }
    }
}

using System;
using System.Collections.Generic;

namespace TestApp
{
    public class PaymentService
    {
        private readonly string _apiKey;
        private readonly List<string> _transactions = new();

        public PaymentService(string apiKey)
        {
            _apiKey = apiKey;
        }

        public string ProcessPayment(decimal amount, string currency)
        {
            var transactionId = Guid.NewGuid().ToString();
            _transactions.Add($"{transactionId}:{amount}:{currency}");
            return transactionId;
        }

        public bool RefundPayment(string transactionId)
        {
            return _transactions.RemoveAll(t => t.StartsWith(transactionId)) > 0;
        }
    }
}

using System;
using System.Collections.Generic;

namespace TestApp
{
    public class OrderService
    {
        private readonly List<string> _orders = new();

        public void AddOrder(string orderId, decimal amount)
        {
            _orders.Add($"{orderId}:{amount}");
        }

        public int GetOrderCount()
        {
            return _orders.Count;
        }
    }
}

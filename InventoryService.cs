using System;
using System.Collections.Generic;
using System.Linq;

namespace TestApp
{
    public class InventoryService
    {
        private readonly Dictionary<string, int> _stock = new();

        public void AddStock(string productId, int quantity)
        {
            if (_stock.ContainsKey(productId))
                _stock[productId] += quantity;
            else
                _stock[productId] = quantity;
        }

        public bool IsInStock(string productId)
        {
            return _stock.ContainsKey(productId) && _stock[productId] > 0;
        }

        public int GetTotalItems()
        {
            return _stock.Values.Sum();
        }
    }
}

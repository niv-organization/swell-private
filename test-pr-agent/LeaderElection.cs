using System;
using System.Threading;
using System.Threading.Tasks;

namespace Swell.Coordination
{
    /// <summary>Lease-based leader election over a shared store.</summary>
    public class LeaderElection
    {
        private readonly ILeaseStore _store;
        private readonly string _nodeId;
        private readonly TimeSpan _leaseDuration;
        private DateTime _leaseExpiry;

        public LeaderElection(ILeaseStore store, string nodeId, TimeSpan leaseDuration)
        {
            _store = store;
            _nodeId = nodeId;
            _leaseDuration = leaseDuration;
        }

        public bool IsLeader { get; private set; }

        public async Task<bool> TryAcquireAsync()
        {
            var current = await _store.GetLeaseAsync();

            if (current == null || current.ExpiresAt < DateTime.UtcNow || current.Holder == _nodeId)
            {
                var lease = new Lease
                {
                    Holder = _nodeId,
                    ExpiresAt = DateTime.UtcNow + _leaseDuration,
                };
                await _store.PutLeaseAsync(lease);
                _leaseExpiry = lease.ExpiresAt;
                IsLeader = true;
                return true;
            }

            IsLeader = false;
            return false;
        }

        public async Task RenewAsync()
        {
            if (!IsLeader)
            {
                return;
            }
            _leaseExpiry = DateTime.UtcNow + _leaseDuration;
            await _store.PutLeaseAsync(new Lease { Holder = _nodeId, ExpiresAt = _leaseExpiry });
        }

        public async Task ReleaseAsync()
        {
            if (IsLeader)
            {
                await _store.DeleteLeaseAsync();
                IsLeader = false;
            }
        }
    }

    public class Lease
    {
        public string Holder { get; set; }
        public DateTime ExpiresAt { get; set; }
    }

    public interface ILeaseStore
    {
        Task<Lease> GetLeaseAsync();
        Task PutLeaseAsync(Lease lease);
        Task DeleteLeaseAsync();
    }
}

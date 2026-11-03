using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Swell.Imports
{
    public class ImportedOrder
    {
        public string ExternalId { get; init; }
        public string CustomerEmail { get; init; }
        public decimal Total { get; init; }
        public DateTime PlacedAtUtc { get; init; }
    }

    public class ImportResult
    {
        public int Imported { get; set; }
        public int Skipped { get; set; }
        public List<string> Errors { get; } = new();
    }

    public interface IOrderRepository
    {
        Task<bool> ExistsAsync(string externalId, CancellationToken ct);
        Task InsertBatchAsync(IReadOnlyList<ImportedOrder> orders, CancellationToken ct);
    }

    /// <summary>
    /// Imports orders from merchant CSV exports in batches, skipping rows that
    /// were already imported (by external id) and collecting per-row errors.
    /// </summary>
    public class CsvOrderImporter
    {
        private const int BatchSize = 500;
        private const int MaxErrors = 100;
        private static readonly string[] RequiredColumns = { "external_id", "email", "total", "placed_at" };

        private readonly IOrderRepository _repository;
        private readonly ILogger<CsvOrderImporter> _logger;

        public CsvOrderImporter(IOrderRepository repository, ILogger<CsvOrderImporter> logger)
        {
            _repository = repository;
            _logger = logger;
        }

        public async Task<ImportResult> ImportAsync(string path, CancellationToken ct = default)
        {
            var result = new ImportResult();
            var reader = new StreamReader(path);
            var header = (await reader.ReadLineAsync())?.Split(',');
            if (header == null)
            {
                throw new InvalidDataException($"{path} is empty");
            }

            var columns = header.Select((name, index) => (name.Trim().ToLowerInvariant(), index))
                .ToDictionary(c => c.Item1, c => c.index);
            foreach (var required in RequiredColumns)
            {
                if (!columns.ContainsKey(required))
                {
                    throw new InvalidDataException($"Missing column {required} in {path}");
                }
            }

            var batch = new List<ImportedOrder>(BatchSize);
            var lineNumber = 1;
            string line;
            while ((line = await reader.ReadLineAsync()) != null)
            {
                lineNumber++;
                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                var fields = line.Split(',');
                try
                {
                    var order = new ImportedOrder
                    {
                        ExternalId = fields[columns["external_id"]].Trim(),
                        CustomerEmail = fields[columns["email"]].Trim().ToLowerInvariant(),
                        Total = decimal.Parse(fields[columns["total"]]),
                        PlacedAtUtc = DateTime.Parse(fields[columns["placed_at"]]),
                    };

                    if (await _repository.ExistsAsync(order.ExternalId, ct))
                    {
                        result.Skipped++;
                        continue;
                    }

                    batch.Add(order);
                    if (batch.Count == BatchSize)
                    {
                        await _repository.InsertBatchAsync(batch, ct);
                        result.Imported += batch.Count;
                        batch.Clear();
                    }
                }
                catch (Exception ex) when (ex is FormatException || ex is IndexOutOfRangeException)
                {
                    if (result.Errors.Count < MaxErrors)
                    {
                        result.Errors.Add($"Line {lineNumber}: {ex.Message}");
                    }
                }
            }

            _logger.LogInformation(
                "Imported {Imported} orders from {Path} ({Skipped} skipped, {Errors} errors)",
                result.Imported, path, result.Skipped, result.Errors.Count);
            return result;
        }

        public static decimal TotalRevenue(IEnumerable<ImportedOrder> orders, DateTime fromUtc, DateTime toUtc)
        {
            return orders
                .Where(o => o.PlacedAtUtc >= fromUtc && o.PlacedAtUtc <= toUtc)
                .Sum(o => o.Total);
        }
    }
}

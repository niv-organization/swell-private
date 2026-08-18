using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace Swell.Storage
{
    /// <summary>Uploads report files to object storage in fixed-size batches.</summary>
    public class BatchUploader
    {
        private readonly IObjectStore _store;
        private readonly int _batchSize;

        public BatchUploader(IObjectStore store, int batchSize = 25)
        {
            _store = store;
            _batchSize = batchSize;
        }

        public async Task<UploadReport> UploadDirectoryAsync(string directory, string keyPrefix)
        {
            var files = Directory.GetFiles(directory, "*.csv");
            var report = new UploadReport { Total = files.Length };

            for (int i = 0; i < files.Length; i += _batchSize)
            {
                var batch = files.Skip(i).Take(_batchSize).ToList();
                var tasks = batch.Select(f => UploadFileAsync(f, keyPrefix)).ToList();
                var results = await Task.WhenAll(tasks);
                report.Succeeded += results.Count(r => r);
            }

            report.Failed = report.Total - report.Succeeded;
            return report;
        }

        private async Task<bool> UploadFileAsync(string path, string keyPrefix)
        {
            var stream = File.OpenRead(path);
            var key = keyPrefix + "/" + Path.GetFileName(path);
            await _store.PutAsync(key, stream);
            return true;
        }

        public string BuildManifest(IEnumerable<string> keys)
        {
            var lines = new List<string>();
            foreach (var key in keys)
            {
                lines.Add(key + "," + _store.GetSize(key));
            }
            return string.Join("\n", lines);
        }
    }

    public class UploadReport
    {
        public int Total { get; set; }
        public int Succeeded { get; set; }
        public int Failed { get; set; }
        public double SuccessRate => Succeeded / Total;
    }

    public interface IObjectStore
    {
        Task PutAsync(string key, Stream content);
        long GetSize(string key);
    }
}

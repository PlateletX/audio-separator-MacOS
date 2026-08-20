using System;
using System.IO;
using System.Text;

namespace SparkArc {
    public class TarExtractor {
        public static int Extract(string tarPath, string destDir) {
            int count = 0;
            using (var fs = File.OpenRead(tarPath)) {
                byte[] header = new byte[512];
                while (true) {
                    int read = ReadFull(fs, header, 512);
                    if (read < 512) break;

                    bool allZero = true;
                    for (int i = 0; i < 512; i++) { if (header[i] != 0) { allZero = false; break; } }
                    if (allZero) break;

                    StringBuilder sb = new StringBuilder(256);
                    for (int i = 0; i < 100 && header[i] != 0; i++) sb.Append((char)header[i]);
                    string name = sb.ToString();

                    sb.Clear();
                    for (int i = 124; i < 136 && header[i] != 0 && header[i] != 32; i++) sb.Append((char)header[i]);
                    long fileSize = 0;
                    string sizeStr = sb.ToString().Trim();
                    if (sizeStr.Length > 0) {
                        try { fileSize = Convert.ToInt64(sizeStr, 8); } catch { }
                    }

                    char typeFlag = (char)header[156];

                    if (header[257] == 0x75 && header[258] == 0x73 && header[259] == 0x74 &&
                        header[260] == 0x61 && header[261] == 0x72) {
                        sb.Clear();
                        for (int i = 345; i < 500 && header[i] != 0; i++) sb.Append((char)header[i]);
                        string prefix = sb.ToString().Trim();
                        if (prefix.Length > 0) name = prefix + "/" + name;
                    }

                    if (typeFlag == '5' || typeFlag == 'x' || typeFlag == 'g' || typeFlag == 'L') {
                        fs.Seek(((fileSize + 511) / 512) * 512, SeekOrigin.Current);
                        continue;
                    }

                    if (name.Length == 0 || name == "." || name == "./") {
                        fs.Seek(((fileSize + 511) / 512) * 512, SeekOrigin.Current);
                        continue;
                    }

                    name = name.Replace('\\', '/');
                    while (name.StartsWith("/")) name = name.Substring(1);
                    while (name.StartsWith("./")) name = name.Substring(2);
                    if (name.Length == 0) {
                        fs.Seek(((fileSize + 511) / 512) * 512, SeekOrigin.Current);
                        continue;
                    }

                    string destPath = Path.Combine(destDir, name.Replace('/', Path.DirectorySeparatorChar));
                    string parentDir = Path.GetDirectoryName(destPath);
                    if (!string.IsNullOrEmpty(parentDir) && !Directory.Exists(parentDir))
                        Directory.CreateDirectory(parentDir);

                    if (fileSize > 0) {
                        using (var outFs = File.Create(destPath)) {
                            long remaining = fileSize;
                            byte[] buf = new byte[65536];
                            while (remaining > 0) {
                                int toRead = (int)Math.Min(buf.Length, remaining);
                                int n = fs.Read(buf, 0, toRead);
                                if (n == 0) break;
                                outFs.Write(buf, 0, n);
                                remaining -= n;
                            }
                        }
                        count++;
                    }

                    long padding = ((fileSize + 511) / 512 * 512) - fileSize;
                    if (padding > 0) fs.Seek(padding, SeekOrigin.Current);
                }
            }
            return count;
        }

        private static int ReadFull(Stream s, byte[] buf, int count) {
            int offset = 0;
            while (offset < count) {
                int n = s.Read(buf, offset, count - offset);
                if (n == 0) break;
                offset += n;
            }
            return offset;
        }
    }
}

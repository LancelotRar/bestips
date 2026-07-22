# bestips

GitHub Actions 自动采集 Cloudflare 优选 IP，每小时 50 分触发。

**输出文件**：`bestips-ipv4.txt`

**来源**：多个公开 IP 池聚合 & 去重 & 地理标注

**技术特点**：
- `requests.Session` + `urllib3.Retry`（自动重试 3 次）
- 多线程并发查询地理位置
- 原子写入（`.tmp` → `replace()`），防止中途失败清空文件
- 类型注解 + docstring
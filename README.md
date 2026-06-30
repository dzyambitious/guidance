# 外媒速览 · 带后端的每日滚动新闻聚合

109 家外媒，每家每日滚动 20 条新闻。新闻由 **GitHub Actions 定时在服务端抓取**，
生成 `feeds.json`，前端页面同源读取——**没有跨域、不依赖公共代理，稳定显示**。
拿不到 `feeds.json` 时（例如本地直接双击打开），页面会自动退回浏览器实时抓取模式。

## 目录结构

```
.
├── index.html                     # 页面（优先读 feeds.json，失败回退实时抓取）
├── feeds.json                     # 由 Actions 自动生成（首次运行后出现）
├── scripts/
│   ├── fetch_feeds.py             # 抓取脚本：官方 RSS 优先，Google News 兜底
│   ├── media.json                 # 109 家媒体清单（名称/网址/域名/图标）
│   └── requirements.txt
└── .github/workflows/
    └── update-feeds.yml           # 定时任务：每小时两次，自动提交 feeds.json
```

## 部署（GitHub Pages，全免费、零服务器）

1. 新建一个 GitHub 仓库，把本目录所有文件按上面的路径放进去，推到 `main` 分支。
2. **Settings → Pages**：Source 选 `Deploy from a branch`，分支选 `main`、目录 `/ (root)`，保存。
3. **Settings → Actions → General → Workflow permissions**：选 `Read and write permissions`，保存
   （让定时任务能把 `feeds.json` 提交回仓库）。
4. **Actions 标签页 → Update feeds → Run workflow**：先手动跑一次，生成首版 `feeds.json`。
5. 打开 Pages 网址（形如 `https://<用户名>.github.io/<仓库名>/`）即可。

之后每小时 `:07`、`:37` 会自动刷新 `feeds.json`，页面顶部会显示「数据更新于 …」。

## 本地预览 / 调试

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_feeds.py --media scripts/media.json --out feeds.json
python -m http.server 8000          # 必须用本地服务器，浏览器不允许 file:// 读取 feeds.json
# 打开 http://localhost:8000/index.html
```

## 自定义

- **抓取频率**：改 `update-feeds.yml` 里的 `cron`（GitHub 定时最短约 5 分钟级，建议 ≥15 分钟）。
- **每家条数**：改 `fetch_feeds.py` 里的 `PER_FEED`（默认 20）。
- **官方 RSS 源**：在 `fetch_feeds.py` 的 `NATIVE` 字典里增/改，质量比 Google News 更好。
- **增删媒体**：编辑 `scripts/media.json`（页面 `index.html` 内也内嵌了同一份清单用于渲染卡片；
  若要增删媒体，两处都要改，或改成都读取同一个 `media.json`）。

## 说明

- `fetch_feeds.py` 在服务端跑，可直接读各家 RSS，没有浏览器跨域限制，命中率远高于纯前端。
- 个别站点没有可用 RSS、也没被 Google News 收录时，该家会是空列表，页面显示「今日暂无更新」。
- 抓取脚本对每家媒体按「官方 RSS → 中文 Google News → 英文 Google News」依次尝试，任一有结果即停。

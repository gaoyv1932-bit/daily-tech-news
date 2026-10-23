# Frontier Daily · 每日前沿资讯

静态资讯站，使用 GitHub Actions 抓取 RSS，并部署到 GitHub Pages。

## 自动更新

- 每天北京时间 **08:17 左右**运行；GitHub 定时任务可能延迟。
- 也可在 Actions → Update news and deploy → Run workflow 手动更新。
- Solidot：AI、科技；Nature Chemistry：化学研究；BBC Business：经济。
- 来源配置在 `feeds.json`。英文简介保留英文并在页面标记，未接入翻译或付费 AI API。
- 显示来源提供的短简介和原文链接；不生成虚构资讯或发布日期。
- 最多保留 24 条，通常 45 天内；失败来源可保留最近 60 天内的旧记录。
- 单个来源失败时保留该来源旧数据并标记；全部失败时任务失败且不覆盖现有文件。
- 数据去重，脚本使用 Python 标准库，无需安装依赖或设置个人密钥。

## 本地运行

```sh
python -m unittest -v test_update_news.py
python update_news.py
python -m http.server 8000
```

打开 `http://localhost:8000`，不要直接双击 HTML（浏览器会限制本地 JSON 请求）。

## 部署

Pages → Build and deployment → Source 选择 **GitHub Actions**。
工作流将更新 `news.json` 和 `news-meta.json`，提交回 main，并发布页面。
使用仓库内置的临时 GITHUB_TOKEN；写入权限只授予更新任务，Pages 权限只授予部署任务。
公共仓库长时间无活动时 GitHub 可能停用定时任务，可在 Actions 中重新启用。

来源：
- https://www.solidot.org/index.rss
- https://www.nature.com/nchem.rss
- https://feeds.bbci.co.uk/news/business/rss.xml

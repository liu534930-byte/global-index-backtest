# 全球与中国核心资产回测

## 发布到 GitHub Pages

1. 在 GitHub 新建公开仓库，例如 `global-index-backtest`。
2. 上传本目录中的 `index.html` 到仓库根目录。
3. 打开仓库的 **Settings → Pages**。
4. 在 **Build and deployment** 中选择 **Deploy from a branch**，分支选择 **main**，目录选择 **/(root)**。
5. 等待 GitHub 生成 `https://你的用户名.github.io/global-index-backtest/` 链接。

网页打开时会读取 Yahoo Finance 与东方财富的真实月度历史行情，因此访客需要联网。免费行情接口可能有短时限流；遇到读取失败时刷新即可。

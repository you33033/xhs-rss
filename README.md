# 小红书 RSS（GitHub Actions 版）

定时把小红书博主的主页抓成 RSS，发布到 GitHub Pages。手机不用常驻任何东西。

## 一、建仓库

1. GitHub 右上角 **+ → New repository**
2. 名字随便，比如 `xhs-rss`，选 **Public**（私有仓库的 Pages 要付费）
3. 建好后把本目录里的文件传上去：
   - 网页版：**Add file → Upload files**，把解压后的所有文件拖进去
   - 注意 `.github/workflows/feed.yml` 必须在 `.github` 目录下，路径不能变

## 二、放 Cookie（Secret）

Cookie 从手机上的「小红书 RSS」页面拿：登录后点「复制 Cookie」。

1. 仓库 **Settings → Secrets and variables → Actions**
2. **New repository secret**
3. Name 填 `XHS_COOKIE`，Secret 粘贴刚才复制的内容

## 三、填博主

编辑 `config.json`：

```json
{
  "feed_limit": 20,
  "users": [
    { "user_id": "5f1a2b3c4d5e6f7a8b9c0d1e", "nickname": "某某博主" }
  ]
}
```

`user_id` 是主页链接
`https://www.xiaohongshu.com/user/profile/` 后面那 24 位。
手机上在本机页面加好博主后，点「复制 config.json」直接粘贴替换整个文件即可。

## 四、开 Pages

1. 仓库 **Settings → Pages**
2. **Source** 选 `Deploy from a branch`
3. 分支选 `gh-pages`，目录 `/ (root)`，保存

第一次运行后 gh-pages 分支才会出现，所以先做第五步再回来设置也行。

## 五、跑一次

1. 仓库 **Actions** 标签 → 左边「更新小红书订阅」→ **Enable workflow**
2. 右边 **Run workflow**
3. 等 1~2 分钟，绿勾就成功了

之后每 3 小时自动跑一次。

## 六、订阅

- 单个博主：`https://<用户名>.github.io/<仓库名>/feeds/<user_id>.xml`
- 全部合成：`https://<用户名>.github.io/<仓库名>/all.xml`
- 网页看列表：`https://<用户名>.github.io/<仓库名>/`

## 常见问题

- **红叉 + 无登录信息**：Cookie 过期了。手机上重新扫码登录，复制新 Cookie 更新 Secret。
- **红叉 + 验证码**：小红书风控，等几小时再手动跑一次。
- **Pages 404**：Pages 还没设好，或分支不是 gh-pages。
- **抓不到某博主**：博主设置了不可见，或链接里的 user_id 不对。
- **安全**：Cookie 只放在 Secret，不要写进 config.json 或任何文件；它等于你的登录态。

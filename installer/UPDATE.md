# MyridTV 增量更新状态

当前实现覆盖 `_internal/static` 中的 HTML、CSS、JS。更新清单使用 Ed25519 签名；客户端先验签，再逐文件比对 SHA-256，只下载内容不同的文件。全部下载和校验完成后才替换。写入中断会从本机备份还原。界面不会被强制刷新，而是在保存工作后提示用户刷新。

更新通道地址内置了默认值（`dearxiaozhou/MyridTV-updates`的发布清单），发布版启动时自动拉起后台检查器，不需要用户配置任何环境变量。`MYRIDTV_UPDATE_FEED_URL` 仅用于覆盖该地址，置为空字符串可显式关闭自动更新。研发源码目录（含 `.git`）不会自动覆盖，本地开发改动保持原样。发布版每 30 分钟检查一次，同一用户数据目录只保留一个检查进程。

界面内的更新入口：底部版本号按钮可点击，会同步跑一次检查并在右下角提示结果（更新就绪/ 已是最新 / 检查失败）。检查不会自动刷新界面，仍由用户在保存当前编辑后手动点「刷新界面」，因此不会打断正在编辑的画布。也可调用 `POST /api/update-check` 触发同一次检查。

发布流水线通过 `installer/make-update-release.py` 生成私有 CI 工件。清单包含当前全部可更新文件，但新版本只生成内容变化的 `blob-*` 文件；未变化的文件沿用上一版清单中的下载地址。发布旧版本资源时必须保留历史 Release，否则跳过多版的客户端无法获取沿用的文件。

公开更新渠道已启用：`dearxiaozhou/MyridTV-updates`（公开仓库），仅发布前端静态资源，不含 Python 源码。后端 `.py` 不走此通道，后端变更仍需重新发布安装包。更新通道只发布 HTML/CSS/JS；前端代码在网页应用中始终可被查看，这是无法回避的。

下载失败会自动重试（最多 4 次，退避 1.5/3/4.5 秒），以应对 CDN 抖动。

签名私钥存放在源码仓库的 Actions Secret `MYRIDTV_UPDATE_SIGNING_KEY`，公钥为根目录 `update-public-key.pub`。请不要把私钥放进发布包或 Git 仓库。

本地验证：

```powershell
python -m unittest tests.test_myridtv_updater -v
python myridtv_updater.py --app-dir <隔离安装目录> --feed <测试清单URL> --allow-local-feed
```

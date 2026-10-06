# MyridTV 增量更新状态

当前实现覆盖 `_internal/static` 中的 HTML、CSS、JS。更新清单使用 Ed25519 签名；客户端先验签，再逐文件比对 SHA-256，只下载内容不同的文件。全部下载和校验完成后才替换。写入中断会从本机备份还原。界面不会被强制刷新，而是在保存工作后提示用户刷新。

`MYRIDTV_UPDATE_FEED_URL` 是发布版启用后台检查的开关。未配置时不启动检查器。研发源码目录也不会自动覆盖。发布版每 30 分钟检查一次，同一用户数据目录只保留一个检查进程。

发布流水线通过 `installer/make-update-release.py` 生成私有 CI 工件。清单包含当前全部可更新文件，但新版本只生成内容变化的 `blob-*` 文件；未变化的文件沿用上一版清单中的下载地址。发布旧版本资源时必须保留历史 Release，否则跳过多版的客户端无法获取沿用的文件。

公开更新渠道尚未启用。现有安装包包含可读的 Python 源文件；把后端补丁上传到公开仓库会公开这些文件。只有确认后端发布形态和公开资源范围后，才能启用自动上传并配置客户端更新地址。前端 HTML、CSS、JS 在网页应用中始终可被查看。

签名私钥存放在源码仓库的 Actions Secret `MYRIDTV_UPDATE_SIGNING_KEY`，公钥为根目录 `update-public-key.pub`。请不要把私钥放进发布包或 Git 仓库。

本地验证：

```powershell
python -m unittest tests.test_myridtv_updater -v
python myridtv_updater.py --app-dir <隔离安装目录> --feed <测试清单URL> --allow-local-feed
```

# V0.8.12 边框与提示词字号验证

## 修改
- 语音节点下拉按钮恢复 1px 主题细边框和轻背景，鼠标悬停/展开时显示强调边框。
- 以 RH 已有的 15px 提示词字号为基准，新增共享字号及 1.55 行距变量，统一 ComfyUI、API 图片/视频、文本节点、剧本、循环提示词、提示词属性、LLM 指令、语音描述与朗读文本，以及上游提示词预览。
- VERSION、首页标签、两项安装器版本、资源缓存标识同步为 V0.8.12。

## 验证
- 官方启动器重新启动了研发版应用。
- python tests/verify_speech_dropdowns_live.py：实际 3107 服务中验证 1px 边框、菜单展开/关闭、键盘焦点、缩放定位和文本输入框的 15px 字号；实际样式下 9 类提示词编辑器字号均为 15px，行高均为 23.25px。
- python tests/e2e_speech.py：在隔离数据目录运行相同应用代码，验证实际点击/编辑、菜单选择、字段保存/重载、文本连线、WAV/MP3 播放与下载、设计/预置/复刻和错误恢复全部通过。
- 截图人工检查：verification-speech-dropdown-v0812.png、verification-prompt-fonts-v0812.png、verification-speech-live-v0812.png。
- 原生桌面窗口截图工具两次返回 foreground window did not report a process id，无法完成原生窗口截图核对。已完成实际运行服务的浏览器页面截图与交互验证。
- 未修改用户节点配置，未调用真实 MiMo 生成接口。

# V0.8.11 语音下拉框验证

- 语音节点的平台、生成方式、音色、格式、台词处理、表演模式、语速、情绪、方言和文本来源采用统一的画布参数按钮及浮层选项样式。
- 按钮采用 30px 高度、11px 字号、8px 圆角、13px 箭头；使用已有主题色和 unified-option 选项样式。
- 菜单挂载于页面浮层，跟随节点位置和缩放，避免被节点内部裁切。支持键盘方向键、首末项、Enter、Escape、Tab 和外部点击关闭；生成和上传期间禁用。
- node --check _internal/static/js/canvas-speech.js：通过。
- python -m unittest tests.test_provider_audio：10 项通过。
- python tests/e2e_speech.py：完整运行应用与本地音频服务验证通过，包括所有可见菜单点击、键盘选择、文字与箭头可见、菜单位置、字段保存与重载、音色设计/预置/复刻、WAV/MP3 播放及下载。
- 使用官方研发版启动器重启本地应用，python tests/verify_speech_dropdowns_live.py 在实际 3107 服务的“MiMo 语音示例”画布中确认菜单展开、Escape 关闭、焦点、缩放定位、所有边界以及无页面错误。该验证未修改用户节点配置，未调用远程 MiMo。
- 截图：verification-speech-dropdown-v0811.png、verification-speech-live-v0811.png，以及 design/preset/clone/settings 截图。
- VERSION、首页版本文字、安装器版本、语音资源缓存参数已同步至 V0.8.11。

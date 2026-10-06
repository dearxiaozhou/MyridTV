# MiMo 语音参数补充 · V0.8.10

## 官方依据

2026-10-01 重新读取：
- 使用指南：https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5
- 接口参数：https://mimo.mi.com/docs/zh-CN/api/audio/tts

硬参数：模型（设计/预置/复刻）、audio.format（WAV/MP3/PCM/PCM16）、audio.voice（预置音色或复刻样本）、audio.optimize_text_preview（仅设计）、stream。
语速、情绪、语言/方言、停顿与表演通过 user 自然语言和 assistant 文本标签控制。接口参数表未提供精确 duration、数值 speed、pitch、volume 或 seed 字段。本轮继续使用非流式完整生成，提供 MP3/WAV 成品。

## 改动

- 没有可选上游文本时隐藏“手写文本”来源下拉框；已连接来源和已断开的选择仍可切换。
- 增加 MP3/WAV 选择，文件格式和下载标签匹配真实输出。
- 增加文本智能优化/自动写词，允许设计模式台词留空；保存并显示 final_text_preview，默认仍原文朗读。
- 增加音色复刻模型、MP3/WAV 样本上传与试听。仅后端读取本地 assets 范围内的样本并转换 Base64，编码后最大 10 MB，画布仅保存本地样本 URL。
- 增加语速、情绪、语言/方言选择，后端将选择转换为自然语言指令，不传入文档未支持的数值字段。
- 预置音色支持唱歌模式，通过官方 (唱歌) 标签传入。
- 增加吸气、叹气、轻笑、哽咽、停顿的台词光标插入按钮，连接上游台词时禁用编辑按钮。
- 修复紧凑播放器按钮被裁切，以及画布同步替换节点对象时输入或生成结果写入旧对象的问题。
- 更新 VERSION、桌面显示版本、安装工程版本与资源缓存。

## 实际验证

- 10 项后端测试通过：tests/test_provider_audio.py。
- 真实浏览器 + 隔离本地应用服务的完整集成测试通过：tests/e2e_speech.py。
- 真实 MP3 测试文件由本地 WAV 编码，用于模拟官方响应；播放器能播放，下载字节一致，扩展名为 .mp3。
- 本地模拟请求逐项验证：三种模型、两种输出格式、自然语言映射、唱歌标签、优化省略 assistant、返回的最终台词、样本 MIME/Base64、样本与选项保存/重载、失败后重试。
- 测试点击焦点、键盘编辑、来源切换、真实端口连线、旧节点横向迁移、标题拖动、同步对象替换后输入/生成，以及播放按钮完整位于卡片内。
- 实际研发版已重启，3107 服务健康，MiMo 三种音频模型均可用。
- 直接在 3107 实际服务打开“MiMo 语音示例”，核对横向布局、三个模式、格式和风格选择，实际点击字段后保留焦点，无通用提示词面板、无页面脚本错误。此检查仅读取和点击焦点，未输入、未生成。
- 桌面截图确认显示 V0.8.10。

截图：verification-speech-live-v0810.png、verification-speech-design-v0810.png、verification-speech-clone-v0810.png、verification-speech-settings-v0810.png。

## 验证边界

本轮未调用真实 MiMo 生成服务。真实模型效果、账号权限、网络和额度尚待用户配置后验证。
网络请求 timeout=240 秒，这是本地请求超时配置，不代表成品语音为 240 秒，也不是官方指定的音频时长。

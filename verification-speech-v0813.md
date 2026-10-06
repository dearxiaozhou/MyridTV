# V0.8.13 语音响应中断处理

## 现象与定位
- 用户原节点的历史日志包含 IncompleteRead(1 bytes read)，底层 HTTP chunk 响应在正文未完成时关闭。
- 真实 MiMo 诊断曾成功返回同一请求的 MP3：65,976 字节、约 8.088 秒；HTTP 200、application/json、Transfer-Encoding: chunked。
- 对比实际前端序列化请求与成功诊断请求：构造后的上游请求完全一致，音色设计、MP3、智能优化=true，两个消息长度分别为 41/19 字。
- 此后通过实际 3107 应用的原节点提交仍遇到不完整响应。无法确认真实生成已恢复，不能宣称生成故障彻底修复。

## 已实施
- 捕获 HTTP IncompleteRead / RemoteDisconnected / 无效 JSON，转换为明确的中文节点错误与 502 状态。
- 如果仅缺少 HTTP 最终分块结束标记，但已经收到完整、可解析 JSON，则恢复该响应；音频仍必须通过完整 WAV/MP3 校验。
- 仅换行、截断 JSON 和不完整音频不能冒充成功或写成音频文件。
- 不自动重复提交付费生成请求，保留输入及已有音频，失败后按钮可重新点击。
- 失败日志记录节点 ID、模型、状态和已脱敏的中文说明，不记录密钥或完整台词。
- VERSION、首页、两项安装器版本与资源缓存参数同步为 V0.8.13。

## 验证
- python -m unittest tests.test_provider_audio：11 项通过。新增真实本地 HTTP 分块中断测试：完整 JSON 缺结束块可恢复；仅换行/截断 JSON 返回中文错误，且每次只有一次请求。
- python tests/e2e_speech.py：完整实际应用与本地服务验证通过，包括中断显示中文、保留原音频、不自动重试、重新启用按钮、完整响应恢复播放，以及既有生成/保存/播放/下载流程。
- tests/verify_speech_real.py 在实际运行服务中用用户原节点验证：仍失败于 MiMo 不完整响应，最后一次 screenshot: verification-speech-real-v0813.png。原节点输入保留、显示中文错误。
- Windows 原生 Schannel 传输也作过诊断，TLS 1.2 连接探测通过，但实际生成仍失败，因此未保留该替代传输。
- 官方请求结构再次对照 https://mimo.mi.com/docs/zh-CN/api/audio/tts 。
- 原生窗口截图工具此前异常；本次已完成真实运行网页截图与节点操作验证。

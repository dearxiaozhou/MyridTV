"""MiMo non-streaming speech synthesis. Keys remain in the local provider store."""
import base64
import binascii
import io
import http.client
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import wave
from uuid import uuid4

import myridtv_asset_resolver
from myridtv_core import ApiError
import myridtv_env
import myridtv_http
import myridtv_media_localize
import myridtv_provider

MODELS = ("mimo-v2.5-tts-voicedesign", "mimo-v2.5-tts", "mimo-v2.5-tts-voiceclone")
FORMATS = ("wav", "mp3")
MAX_VOICE_BASE64 = 10_000_000
STYLE_OPTIONS = {
    "speed": {"slow":"语速缓慢", "normal":"语速适中", "fast":"语速较快"},
    "emotion": {"calm":"情绪平静", "happy":"开心", "sad":"悲伤", "angry":"愤怒", "fear":"恐惧", "surprise":"惊讶", "tired":"疲惫", "tender":"温柔"},
    "dialect": {"mandarin":"普通话", "cantonese":"粤语", "northeastern":"东北话", "sichuan":"四川话", "henan":"河南话"},
}
VOICES = ("mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean")


class AudioError(Exception):
    def __init__(self, detail, status=400):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def is_mimo(payload):
    host = urllib.parse.urlparse(str(payload.get("base_url") or "")).hostname or ""
    return host == "api.xiaomimimo.com" or str(payload.get("provider_id") or "").lower() == "mimo"


def _response_json(raw):
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise AudioError("MiMo 响应中断或内容不完整，未收到完整音频，请稍后重新生成", 502) from None
    if not isinstance(result, dict):
        raise AudioError("MiMo 返回了无效响应，请稍后重新生成", 502)
    return result


def request_json(url, method="GET", payload=None, headers=None, timeout=30):
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        if host != "api.xiaomimimo.com":
            return myridtv_http.request_json(url, method=method, payload=payload, headers=headers, timeout=timeout)
        # Local OpenSSL/TLS 1.3 reports BAD_RECORD_MAC on this service. TLS 1.2
        # retains certificate verification and avoids that compatibility failure.
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type":"application/json", "Accept":"application/json", **(headers or {})})
        with urllib.request.urlopen(req, context=context, timeout=timeout) as response:
            return _response_json(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError("MiMo HTTP " + str(exc.code)) from exc
    except http.client.IncompleteRead as exc:
        # Some chunked responses close after the complete JSON but omit their
        # final chunk marker. Recover only parseable JSON; audio is still fully
        # validated by decode_audio. A heartbeat or truncated payload must fail.
        # Never resubmit a generation request automatically.
        return _response_json(exc.partial)
    except (json.JSONDecodeError, UnicodeError):
        raise AudioError("MiMo 响应内容不完整，未收到完整音频，请稍后重新生成", 502) from None
    except (http.client.RemoteDisconnected, http.client.BadStatusLine):
        raise AudioError("MiMo 连接在返回音频前中断，请稍后重新生成", 502) from None


def probe(payload):
    # Share discovery and classification with every custom compatible provider.
    # Retain only the transport workaround required by this host.
    import myridtv_volcengine
    return myridtv_volcengine.openai_probe_payload(payload, request_json=request_json)


def mp3_duration(raw):
    """Validate complete MPEG Layer III frame headers, without a codec dependency."""
    start = 0
    if raw.startswith(b"ID3"):
        if len(raw) < 10 or any(v & 128 for v in raw[6:10]):
            raise ValueError("invalid ID3")
        size = sum(v << shift for v, shift in zip(raw[6:10], (21,14,7,0)))
        start = 10 + size + (10 if raw[5] & 16 else 0)
    duration, frames, offset = 0.0, 0, start
    while offset + 4 <= len(raw):
        header = int.from_bytes(raw[offset:offset+4], "big")
        version, layer = (header >> 19) & 3, (header >> 17) & 3
        index, rate_index = (header >> 12) & 15, (header >> 10) & 3
        valid = header >> 21 == 2047 and version != 1 and layer == 1 and 0 < index < 15 and rate_index < 3
        if not valid:
            if frames:
                break  # trailing tags are not MPEG audio frames
            offset += 1
            if offset > start + 4096:
                break
            continue
        rates = (44100,48000,32000)
        rate = rates[rate_index] // (1 if version == 3 else 2 if version == 2 else 4)
        table = (0,32,40,48,56,64,80,96,112,128,160,192,224,256,320) if version == 3 else (0,8,16,24,32,40,48,56,64,80,96,112,128,144,160)
        length = (144 if version == 3 else 72) * table[index] * 1000 // rate + ((header >> 9) & 1)
        if offset + length > len(raw):
            raise ValueError("truncated MP3")
        duration += (1152 if version == 3 else 576) / rate
        frames += 1
        offset += length
    if frames < 2:
        raise ValueError("invalid MP3")
    return duration


def audio_duration(raw, format):
    if format == "mp3":
        return mp3_duration(raw)
    with wave.open(io.BytesIO(raw), "rb") as wav:
        frames, rate = wav.getnframes(), wav.getframerate()
        if frames <= 0 or rate <= 0 or len(wav.readframes(frames)) < frames * wav.getnchannels() * wav.getsampwidth():
            raise ValueError("empty or truncated WAV")
        return frames / rate


def clone_voice(reference_url):
    parsed = urllib.parse.urlparse(str(reference_url or ""))
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/assets/"):
        raise AudioError("请上传本地 MP3 或 WAV 音色样本")
    try:
        path = myridtv_asset_resolver.resolve_user_asset_path(reference_url)
        format = path.suffix.lower().lstrip(".")
        if format not in FORMATS:
            raise AudioError("音色样本仅支持 MP3 或 WAV")
        if (path.stat().st_size + 2) // 3 * 4 + 32 > MAX_VOICE_BASE64:
            raise AudioError("音色样本编码后不能超过 10 MB，请上传更短的音频")
        raw = path.read_bytes()
        audio_duration(raw, format)
        mime = "audio/mpeg" if format == "mp3" else "audio/wav"
        voice = "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")
        if len(voice) > MAX_VOICE_BASE64:
            raise AudioError("音色样本编码后不能超过 10 MB")
        return voice
    except (ApiError, OSError, ValueError, wave.Error, EOFError):
        raise AudioError("音色样本不存在或不是有效音频，请重新上传 MP3 或 WAV") from None


def build_request(payload):
    if not isinstance(payload, dict):
        raise AudioError("语音参数必须是对象")
    model = str(payload.get("model") or MODELS[0]).strip()
    if not model:
        raise AudioError("请选择已配置的语音模型")
    format = str(payload.get("format") or "wav").lower()
    if format not in FORMATS:
        raise AudioError("输出格式请选择 WAV 或 MP3")
    optimize = payload.get("optimize_text_preview", False)
    if not isinstance(optimize, bool):
        raise AudioError("文本智能优化参数必须为布尔值")
    if optimize and model != MODELS[0]:
        raise AudioError("文本智能优化仅支持音色设计")
    text = str(payload.get("text") or "").strip()
    style = str(payload.get("style") or "").strip()
    if not text and not (model == MODELS[0] and optimize):
        raise AudioError("请填写朗读文本，或连接并选择上游文本")
    if len(text) > 10000 or len(style) > 4000:
        raise AudioError("请将台词控制在 10000 字以内，声音描述控制在 4000 字以内")
    if model == MODELS[0] and not style:
        raise AudioError("音色设计需要填写声音描述")
    guidance = []
    for key, options in STYLE_OPTIONS.items():
        selected = str(payload.get(key) or "")
        if selected:
            if selected not in options:
                raise AudioError("无效的语速、情绪或方言选项")
            guidance.append(options[selected])
    if guidance:
        style += ("\n" if style else "") + "表演要求：" + "；".join(guidance) + "。"
    if payload.get("singing"):
        if model != MODELS[1]:
            raise AudioError("唱歌模式仅支持预置音色")
        if not re.match(r"^[（(\[]\s*(唱歌|sing|singing)[）)\]]", text, re.I):
            text = "(唱歌)" + text
    audio = {"format": format}
    if model == MODELS[0]:
        audio["optimize_text_preview"] = optimize
    elif model == MODELS[2]:
        audio["voice"] = clone_voice(payload.get("reference_url"))
    else:
        voice = str(payload.get("voice") or "mimo_default")
        if voice not in VOICES:
            raise AudioError("请选择有效的预置音色")
        audio["voice"] = voice
    messages = ([{"role": "user", "content": style}] if style else [])
    if text:
        messages.append({"role": "assistant", "content": text})
    return {"model": model, "messages": messages, "audio": audio, "stream": False}


def decode_audio(result, format="wav"):
    try:
        encoded = result["choices"][0]["message"]["audio"]["data"]
        raw = base64.b64decode(encoded, validate=True)
        return raw, audio_duration(raw, format)
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error, wave.Error, EOFError):
        raise AudioError("MiMo 未返回有效的 " + format.upper() + " 音频，请检查模型权限或重试", 502) from None


def generate(payload):
    body = build_request(payload)
    pid = str(payload.get("provider_id") or "").strip()
    provider = next((p for p in myridtv_provider.read_api_providers() if p.get("id") == pid), None)
    if not provider or provider.get("enabled") is False:
        raise AudioError("请在 API 设置中选择并启用 MiMo 平台")
    if body["model"] not in (provider.get("audio_models") or []):
        raise AudioError("当前平台未配置此音频模型，请在 API 设置中保存音频模型")
    # Read only this platform's key, never fall back to an Agent/other provider key.
    values = myridtv_env.read_env_values()
    key = str(values.get(myridtv_env.provider_key_env_name(pid)) or "").strip()
    if not key:
        raise AudioError("尚未配置 MiMo API Key，请打开 API 设置，选择 MiMo 并保存密钥")
    base = str(provider.get("base_url") or "").strip().rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise AudioError("请在 API 设置中填写有效的 MiMo 请求地址")
    try:
        result = request_json(base + "/chat/completions", method="POST", payload=body,
                                          headers={"Authorization": "Bearer " + key}, timeout=240)
    except RuntimeError as exc:
        upstream = getattr(exc.__cause__, "code", None)
        details = {401: "MiMo 密钥无效，请在 API 设置中更新密钥", 403: "MiMo 拒绝访问，请检查模型权限",
                   429: "MiMo 请求过于频繁或额度不足，请稍后重试", 400: "MiMo 拒绝了语音参数，请检查文本和音色描述",
                   404: "MiMo 接口或模型不存在，请检查请求地址和音频模型"}
        raise AudioError(details.get(upstream, "MiMo 服务暂时不可用，请稍后重试"), 502) from None
    except (TimeoutError, socket.timeout):
        raise AudioError("语音生成超时，请稍后重试；重新提交可能产生新的调用", 504) from None
    except (urllib.error.URLError, ssl.SSLError, OSError):
        raise AudioError("无法连接 MiMo，请检查网络和请求地址", 502) from None
    format = body["audio"]["format"]
    raw, duration = decode_audio(result, format)
    cid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(payload.get("canvas_id") or ""))[:100]
    folder = myridtv_media_localize.canvas_output_folder_name(payload.get("canvas_title") or "", cid)
    output_dir = myridtv_media_localize.asset_output_media_dir("audio", folder)
    name = "MiMo-" + uuid4().hex[:12] + "." + format
    path = output_dir / name
    path.write_bytes(raw)
    item = {"url": myridtv_media_localize.asset_output_url(name, "audio", canvas_folder=folder),
            "name": name, "kind": "audio", "local_path": str(path), "duration": round(duration, 3),
            "generatedResult": True, "provider_id": pid, "model": body["model"], "format":format}
    preview = str(result.get("choices", [{}])[0].get("message", {}).get("final_text_preview") or "")
    return {"ok": True, "kind": "audio", "items": [item], "audios": [item], "urls": [item["url"]], "final_text_preview":preview}

"""Speech contracts and failure behavior; no remote API requests."""
import base64
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import myridtv_provider_audio as audio
import myridtv_provider as provider


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\0\0" * 2400)
    return buf.getvalue()


class SpeechTests(unittest.TestCase):
    def test_interrupted_chunked_responses_never_resubmit_or_accept_partial_audio(self):
        calls=[]
        complete={'choices':[{'message':{'audio':{'data':base64.b64encode(wav_bytes()).decode()}}}]}
        class BrokenChunkHandler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length',0)))
                calls.append(self.path)
                self.send_response(200);self.send_header('Transfer-Encoding','chunked');self.end_headers()
                data=b'\n'+json.dumps(complete).encode() if self.path=='/complete' else b'\n' if self.path=='/heartbeat' else b'{"choices":['
                self.wfile.write(hex(len(data))[2:].encode()+b'\r\n'+data+b'\r\n');self.wfile.flush()
                self.close_connection=True  # missing final zero-size HTTP chunk
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),BrokenChunkHandler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            root='http://127.0.0.1:'+str(server.server_port)
            result=audio.request_json(root+'/complete',method='POST',payload={})
            raw,duration=audio.decode_audio(result)
            self.assertEqual(raw,wav_bytes());self.assertEqual(duration,.1)
            for path in ['/heartbeat','/truncated']:
                with self.assertRaisesRegex(audio.AudioError,'响应中断或内容不完整') as caught:
                    audio.request_json(root+path,method='POST',payload={})
                self.assertEqual(caught.exception.status,502)
                self.assertNotIn('IncompleteRead',str(caught.exception))
            self.assertEqual(calls,['/complete','/heartbeat','/truncated'])
        finally:
            server.shutdown();server.server_close();worker.join()

    def test_script_and_design_contract(self):
        body = audio.build_request({"text":"[轻笑]你好。", "style":"沉稳的青年男性"})
        self.assertEqual(body["messages"], [{"role":"user", "content":"沉稳的青年男性"}, {"role":"assistant", "content":"[轻笑]你好。"}])
        self.assertEqual(body["audio"], {"format":"wav", "optimize_text_preview":False})
        self.assertFalse(body["stream"])

    def test_preset_accepts_optional_direction(self):
        body = audio.build_request({"model":"mimo-v2.5-tts", "text":"你好", "voice":"茉莉"})
        self.assertEqual(body["audio"], {"format":"wav", "voice":"茉莉"})
        self.assertEqual(body["messages"], [{"role":"assistant", "content":"你好"}])

    def test_formats_optimization_and_director_controls(self):
        body = audio.build_request({'model':audio.MODELS[0], 'style':'清冷女声', 'optimize_text_preview':True, 'format':'mp3', 'speed':'slow', 'emotion':'tired', 'dialect':'cantonese'})
        self.assertEqual(body['audio'], {'format':'mp3', 'optimize_text_preview':True})
        self.assertEqual(body['messages'], [{'role':'user', 'content':'清冷女声\n表演要求：语速缓慢；疲惫；粤语。'}])
        singing=audio.build_request({'model':audio.MODELS[1], 'text':'[轻笑]歌词', 'singing':True})
        self.assertEqual(singing['messages'][-1]['content'],'(唱歌)[轻笑]歌词')
        for kwargs in [{'format':'unknown'},{'optimize_text_preview':'false'},{'speed':'unknown'},{'model':audio.MODELS[1],'optimize_text_preview':True},{'singing':True}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(audio.AudioError):
                audio.build_request({'text':'台词','style':'女声',**kwargs})

    def test_clone_only_reads_local_audio_and_checks_encoded_size(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'sample.wav'; path.write_bytes(wav_bytes())
            with patch.object(audio.myridtv_asset_resolver,'resolve_user_asset_path',return_value=path) as resolve:
                body=audio.build_request({'model':audio.MODELS[2], 'text':'hi', 'reference_url':'/assets/sample.wav'})
                self.assertEqual(body['audio']['voice'],'data:audio/wav;base64,'+base64.b64encode(wav_bytes()).decode())
                for source in ['https://example.com/sample.wav','file:///private.wav','/other/sample.wav','']:
                    with self.assertRaises(audio.AudioError):audio.clone_voice(source)
                self.assertEqual(resolve.call_count,1)
                with patch.object(audio,'MAX_VOICE_BASE64',100):
                    with self.assertRaisesRegex(audio.AudioError,'10 MB'):audio.clone_voice('/assets/sample.wav')
                path.write_bytes(b'not audio')
                with self.assertRaises(audio.AudioError):audio.clone_voice('/assets/sample.wav')

    def test_mp3_frames_and_format_mismatch(self):
        raw=(bytes.fromhex('fffb9064')+bytes(413))*4
        result={'choices':[{'message':{'audio':{'data':base64.b64encode(raw).decode()}}}]}
        decoded,duration=audio.decode_audio(result,'mp3')
        self.assertEqual(decoded,raw)
        self.assertAlmostEqual(duration,4*1152/44100)
        with self.assertRaises(audio.AudioError):audio.decode_audio(result,'wav')
        for broken in [b'ID3',raw[:20],b'not MP3']:
            with self.assertRaises(ValueError):audio.mp3_duration(broken)

    def test_rejects_empty_unsupported_and_invalid_voice(self):
        for payload in [{"text":""}, {"text":"hi", "style":""},
                        {"text":"hi", "model":"mimo-v2.5-tts", "voice":"unknown"}]:
            with self.subTest(payload=payload), self.assertRaises(audio.AudioError):
                audio.build_request(payload)

    def test_new_user_configured_model_is_not_blocked_by_builtin_allowlist(self):
        body=audio.build_request({'model':'mimo-future-tts','text':'你好'})
        self.assertEqual(body['model'],'mimo-future-tts')

    def test_custom_mimo_models_are_user_owned_without_injection(self):
        p = provider.sanitize_api_provider_record({"id":"custom-mimo", "base_url":"https://api.xiaomimimo.com/v1"})
        self.assertEqual(p["audio_models"], [])
        self.assertEqual(p["image_models"], [])
        saved = provider.sanitize_api_provider_record({**p, "audio_models":[audio.MODELS[1]]})
        self.assertEqual(saved["audio_models"], [audio.MODELS[1]])
        empty = provider.sanitize_api_provider_record({**p, "audio_models":[]})
        self.assertEqual(empty["audio_models"], [])

    def test_missing_key_never_submits(self):
        p = {"id":"fixture", "audio_models":list(audio.MODELS), "base_url":"http://127.0.0.1/v1"}
        with patch.object(audio.myridtv_provider, "read_api_providers", return_value=[p]), patch.object(audio.myridtv_env, "read_env_values", return_value={"MYRIDTV_AGENT_API_KEY":"unrelated-key"}), patch.object(audio,"request_json") as request:
            with self.assertRaisesRegex(audio.AudioError,"尚未配置"):
                audio.generate({"provider_id":"fixture", "text":"hi", "style":"calm"})
            request.assert_not_called()

    def test_wav_is_written_and_returns_local_url(self):
        raw = wav_bytes()
        result = {"choices":[{"message":{"audio":{"data":base64.b64encode(raw).decode()}}}]}
        p = {"id":"fixture", "audio_models":list(audio.MODELS), "base_url":"http://127.0.0.1/v1"}
        with tempfile.TemporaryDirectory() as temp, patch.object(audio.myridtv_provider,"read_api_providers", return_value=[p]), patch.object(audio.myridtv_env,"read_env_values", return_value={"API_PROVIDER_FIXTURE_KEY":"mock-only"}), patch.object(audio,"request_json", return_value=result) as request, patch.object(audio.myridtv_media_localize,"asset_output_media_dir", return_value=Path(temp)), patch.object(audio.myridtv_media_localize,"asset_output_url", side_effect=lambda name,*a,**kw:'/assets/'+name):
            output = audio.generate({"provider_id":"fixture", "text":"你好", "style":"沉稳", "canvas_id":"canvas-1"})
            self.assertEqual(Path(output["items"][0]["local_path"]).read_bytes(), raw)
            self.assertEqual(output["items"][0]["duration"], .1)
            self.assertTrue(output["urls"][0].endswith('.wav'))
            self.assertNotIn('mock-only',str(output))
            self.assertEqual(request.call_args.kwargs["headers"]["Authorization"],"Bearer mock-only")

    def test_invalid_audio_and_rate_limit_are_clear_and_redacted(self):
        with self.assertRaisesRegex(audio.AudioError,"有效的 WAV"):
            audio.decode_audio({"choices":[{"message":{"audio":{"data":"not-base64"}}}]})
        cause = urllib.error.HTTPError('http://fixture',429,'mock-key-leak',{},None)
        error = RuntimeError('mock-key-leak')
        error.__cause__ = cause
        p = {"id":"fixture", "audio_models":list(audio.MODELS), "base_url":"http://127.0.0.1/v1"}
        with patch.object(audio.myridtv_provider,"read_api_providers", return_value=[p]), patch.object(audio.myridtv_env,"read_env_values", return_value={"API_PROVIDER_FIXTURE_KEY":"mock-only"}), patch.object(audio,"request_json", side_effect=error):
            with self.assertRaisesRegex(audio.AudioError,"频繁或额度不足") as caught:
                audio.generate({"provider_id":"fixture", "text":"hi", "style":"calm"})
            self.assertNotIn('mock-key', str(caught.exception))


if __name__ == '__main__':
    unittest.main()

"""Real catalog data and explicit custom lists replace provider-specific presets."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import myridtv_provider as providers
import myridtv_provider_audio as audio
import myridtv_volcengine as discovery


class DiscoveryTests(unittest.TestCase):
    def test_mimo_uses_upstream_catalog_including_new_chat_and_audio(self):
        ids=['mimo-v2.6-pro','mimo-future-tts','mimo-v2.5-asr']
        with patch.object(audio,'request_json',return_value={'data':[{'id':m} for m in ids]}):
            data=audio.probe({'provider_id':'custom-mimo','base_url':'https://api.xiaomimimo.com/v1','api_key':'fixture'})
        self.assertEqual(data['all'],ids)
        self.assertEqual(data['chat_models'],ids[:1])
        self.assertEqual(data['audio_models'],ids[1:])
        self.assertNotIn(audio.MODELS[0],data['all'])

    def test_missing_catalog_is_failure_without_presets(self):
        for response in ({'error':'no models'}, {'data':[]}):
            with patch.object(audio,'request_json',return_value=response):
                data=audio.probe({'base_url':'https://api.xiaomimimo.com/v1','api_key':'fixture'})
            self.assertEqual(data['all'],[])
            self.assertEqual(data['audio_models'],[])
        self.assertFalse(discovery.openai_probe_payload({'base_url':''})['ok'])

    def test_custom_plan_does_not_use_native_credentials_or_model_presets(self):
        with patch.object(discovery,'_r_read_chat_key',return_value='custom-key'), patch.object(discovery.myridtv_http,'request_json',return_value={'data':[{'id':'my-plan-model'}]}) as request:
            data=discovery.volcengine_fetch_models({'provider_id':'custom-plan','base_url':'https://fixture/api/plan/v3'})
        self.assertEqual(data['all'],['my-plan-model'])
        self.assertEqual(request.call_args.kwargs['headers'],{'Authorization':'Bearer custom-key'})

    def test_explicit_empty_custom_lists_stay_empty(self):
        p={'id':'custom-mimo','base_url':'https://api.xiaomimimo.com/v1','audio_models':[],'chat_models':['my-new-model']}
        clean=providers.ensure_api_provider_models([providers.sanitize_api_provider_record(p)])[0]
        self.assertEqual(clean['audio_models'],[])
        self.assertEqual(clean['chat_models'],['my-new-model'])

if __name__=='__main__':
    unittest.main()

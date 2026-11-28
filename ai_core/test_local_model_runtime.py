"""Tiny locally-created checkpoints exercise actual inference without downloads.

These tests check integration, not the accuracy of the user's trained weights.
They run in the optional local-ai CI job and skip when its packages are absent.
"""
import io
from pathlib import Path
import shutil
import tempfile
import time
import wave
from unittest import skipUnless
from unittest.mock import patch, Mock
import importlib.util

from django.test import SimpleTestCase, override_settings
from PIL import Image, ImageDraw, ImageFont

HAS_LOCAL_AI = all(importlib.util.find_spec(name) for name in ('torch', 'transformers', 'numpy', 'tokenizers'))


@skipUnless(HAS_LOCAL_AI, 'Install requirements-local-ai.txt to exercise model inference')
@override_settings(AI_LOCAL_ENABLED=True, AI_LOCAL_DEVICE='cpu', AI_LOCAL_MAX_TOKENS=8)
class LocalModelRuntimeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import torch
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from tokenizers.pre_tokenizers import Whitespace
        from transformers import RobertaTokenizerFast, TrOCRProcessor, ViTImageProcessor, ViTConfig, ViTModel, TrOCRConfig, TrOCRForCausalLM, VisionEncoderDecoderModel
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        cls.directory = Path(cls.folder.name) / 'best_model'
        torch.set_num_threads(1)
        tokenizer = Tokenizer(WordLevel({'<s>': 0, '<pad>': 1, '</s>': 2, '<unk>': 3, '<mask>': 4,
            'department': 5, 'issue': 6, 'join': 7}, unk_token='<unk>'))
        tokenizer.pre_tokenizer = Whitespace()
        wrapped = RobertaTokenizerFast(tokenizer_object=tokenizer, bos_token='<s>', eos_token='</s>',
            pad_token='<pad>', unk_token='<unk>', mask_token='<mask>')
        processor = TrOCRProcessor(image_processor=ViTImageProcessor(size={'height': 32, 'width': 32}), tokenizer=wrapped)
        encoder = ViTModel(ViTConfig(image_size=32, patch_size=4, hidden_size=16,
            num_hidden_layers=1, num_attention_heads=2, intermediate_size=32))
        decoder = TrOCRForCausalLM(TrOCRConfig(vocab_size=8, d_model=16, decoder_layers=1,
            decoder_attention_heads=2, decoder_ffn_dim=32, max_position_embeddings=64,
            decoder_start_token_id=2, bos_token_id=0, eos_token_id=2, pad_token_id=1))
        model = VisionEncoderDecoderModel(encoder=encoder, decoder=decoder)
        model.config.decoder_start_token_id = 2
        model.config.eos_token_id = 2
        model.config.pad_token_id = 1
        model.generation_config.decoder_start_token_id = 2
        model.generation_config.eos_token_id = 2
        model.generation_config.pad_token_id = 1
        model.save_pretrained(cls.directory, safe_serialization=True)
        processor.save_pretrained(cls.directory)
        from .local_recognition import _load_model
        cls.addClassCleanup(_load_model.cache_clear)

    @staticmethod
    def page():
        image = Image.new('RGB', (800, 350), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=32)
        draw.text((30, 25), 'department', font=font, fill='black')
        draw.text((30, 135), 'issue', font=font, fill='black')
        draw.text((30, 245), 'join', font=font, fill='black')
        return image

    def test_actual_saved_processor_and_checkpoint_load_offline_and_generate(self):
        from .local_recognition import inspect_model, load_local_model, recognize_image
        with override_settings(AI_LOCAL_VOCAB_MODEL_DIR=str(self.directory)), patch('huggingface_hub.file_download.http_get', side_effect=AssertionError('Unexpected download')):
            self.assertEqual(inspect_model('vocabulary')['status'], 'ready')
            processor, model, device = load_local_model('vocabulary')
            self.assertEqual(device, 'cpu')
            self.assertFalse(model.training)
            self.assertEqual(model.generation_config.decoder_start_token_id, 2)
            self.assertIs(load_local_model('vocabulary')[1], model)
            rows, limited = recognize_image(self.page(), time.monotonic()+30)
            self.assertGreaterEqual(len(rows), 3)
            self.assertFalse(limited)
            self.assertTrue(all(isinstance(row['text'], str) and len(row['box']) == 4 for row in rows))

    def test_blank_photo_is_not_invented_as_a_text_line_and_limit_is_explicit(self):
        from .local_recognition import line_regions, recognize_image
        self.assertEqual(line_regions(Image.new('RGB', (500, 500), 'white')), [])
        with override_settings(AI_LOCAL_VOCAB_MODEL_DIR=str(self.directory)):
            rows, limited = recognize_image(self.page(), time.monotonic()+30, max_crops=1)
        self.assertEqual(len(rows), 1)
        self.assertTrue(limited)

    @skipUnless(shutil.which('ffmpeg'), 'FFmpeg is optional for Whisper assistance')
    def test_real_ffmpeg_decodes_browser_audio_and_rejects_overlong_audio(self):
        import numpy as np
        from .local_recognition import _decode_audio, LocalRecognitionError
        stream = io.BytesIO()
        samples = (np.sin(np.arange(32000) * 440 * 2*np.pi / 16000)*16000).astype('<i2')
        with wave.open(stream, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(samples.tobytes())
        decoded = _decode_audio(stream.getvalue(), time.monotonic()+10)
        self.assertEqual(len(decoded), 32000)
        with override_settings(AI_LOCAL_MAX_AUDIO_SECONDS=1), self.assertRaises(LocalRecognitionError) as raised:
            _decode_audio(stream.getvalue(), time.monotonic()+10)
        self.assertEqual(raised.exception.code, 'audio_limit')

    def test_whisper_feature_extraction_keeps_audio_beyond_thirty_seconds(self):
        import numpy as np
        import torch
        from .local_recognition import recognize_audio
        from transformers import WhisperFeatureExtractor
        processor = Mock()
        processor.feature_extractor = Mock(wraps=WhisperFeatureExtractor())
        processor.batch_decode.return_value = ['Full recording transcript.']
        model = Mock()
        model.config.max_target_positions = 448
        model.generate.return_value = torch.tensor([[1, 2]])
        with patch('ai_core.local_recognition.load_local_model', return_value=(processor, model, 'cpu')), patch(
                'ai_core.local_recognition._decode_audio', return_value=np.zeros(16000*45, dtype=np.float32)):
            self.assertEqual(recognize_audio(b'audio', time.monotonic()+30), 'Full recording transcript.')
        self.assertFalse(processor.feature_extractor.call_args.kwargs['truncation'])
        self.assertGreater(model.generate.call_args.kwargs['input_features'].shape[-1], 3000)
        self.assertTrue(model.generate.call_args.kwargs['return_timestamps'])
        self.assertNotIn('prompt_ids', model.generate.call_args.kwargs)

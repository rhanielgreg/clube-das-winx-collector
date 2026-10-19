import unittest
import json
from pathlib import Path
from unittest.mock import patch

from collector import extract, supabase_headers
from stats import confirmed_stats


class CollectorExtractionSafetyTests(unittest.TestCase):
    def test_modern_secret_is_not_sent_as_jwt(self):
        with patch.dict('os.environ', {'SUPABASE_SERVICE_ROLE_KEY': 'sb_secret_test'}):
            self.assertNotIn('Authorization', supabase_headers())
            self.assertEqual(supabase_headers()['apikey'], 'sb_secret_test')

    def test_legacy_key_keeps_bearer_compatibility(self):
        with patch.dict('os.environ', {'SUPABASE_SERVICE_ROLE_KEY': 'legacy-test-jwt'}):
            self.assertEqual(supabase_headers()['Authorization'], 'Bearer legacy-test-jwt')

    def test_anonymizes_account_and_does_not_invent_stats(self):
        result = extract([('steam-user', 'Bloom', 0, b'opaque-data')], 'secret-salt')
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertNotIn('steam-user', row.values())
        self.assertEqual(row['p_character_name'], 'Bloom')
        self.assertTrue(row['p_alive'])
        self.assertIsNone(row['p_kills_total'])
        self.assertIsNone(row['p_survival_seconds'])

    def test_skips_incomplete_identification(self):
        result = extract([(None, 'Bloom', 0, b''), ('user', '', 0, b'')], 'secret-salt')
        self.assertEqual(result, [])

    def test_anonymized_real_ttf_samples(self):
        samples = json.loads((Path(__file__).parent / 'fixtures' / 'ttf_only.json').read_text())
        for sample in samples:
            with self.subTest(total=sample['expected_total']):
                parsed = confirmed_stats(bytes.fromhex(sample['ttf_only_hex']))
                self.assertEqual(parsed['p_kills_total'], sample['expected_total'])
                self.assertIsNone(parsed['p_survival_seconds'])

    def test_rejects_truncated_blob(self):
        self.assertIsNone(confirmed_stats(b'\x00\x00\x0dTTF_KillStats\x02')['p_kills_total'])


if __name__ == '__main__':
    unittest.main()

import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'desktop'))
from introductions import quick_intro, intro_key


class IntroTests(unittest.TestCase):
    def test_chinese_author_intro_is_preserved_without_model_claim(self):
        text, source = quick_intro(dict(full_name='a/app', description='这是一个帮助个人管理知识和笔记的软件。'))
        self.assertIn('管理知识', text); self.assertEqual(source, '作者简介')

    def test_english_description_gets_immediate_chinese_topic_hint(self):
        text, source = quick_intro(dict(full_name='a/app', description='Local notes with backlinks and a knowledge base.'))
        self.assertIn('整理笔记与知识', text); self.assertEqual(source, '按简介主题整理')

    def test_description_change_invalidates_cached_translation(self):
        self.assertNotEqual(intro_key(dict(full_name='a/b',description='Old')),intro_key(dict(full_name='a/b',description='New')))

    def test_missing_description_does_not_invent_a_purpose(self):
        text, source=quick_intro(dict(full_name='a/b',description=None))
        self.assertIn('作者尚未提供简介',text); self.assertEqual(source,'待 AI 解读')


if __name__ == '__main__': unittest.main()

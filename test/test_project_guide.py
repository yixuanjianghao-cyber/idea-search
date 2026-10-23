import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'desktop'))
from project_guide import project_guide


class GuideTests(unittest.TestCase):
    def test_examples_explain_uses_and_individual_case_workflow(self):
        d = dict(kind='examples', what='Examples for developers.', readme='# Cookbook\n\n## Tool use\nUse external functions.\n## Retrieval augmented generation\nUse documents.')
        guide = project_guide(d)
        self.assertEqual(guide['kind_label'], '示例与教程')
        self.assertEqual(len(guide['capabilities']), 2)
        self.assertIn('案例', guide['usage'])
        self.assertIn('参考相关代码示例', guide['capabilities'][0]['detail'])

    def test_sponsor_abilities_are_excluded_and_real_project_features_retained(self):
        guide = project_guide(dict(kind='unknown', readme='# Tool\n\n提供会话管理和供应商切换。\n## Sponsors\nSponsor supports multimodal vision agents.\n### Partner\nRAG included.\n## 功能\n支持界面增强。'))
        titles = [c['title'] for c in guide['capabilities']]
        self.assertIn('管理会话', titles)
        self.assertIn('管理模型供应商', titles)
        self.assertIn('调整使用界面', titles)
        self.assertNotIn('理解图片内容', titles)
        self.assertNotIn('组织智能体任务', titles)

    def test_missing_readme_does_not_invent_features(self):
        guide = project_guide(dict(kind='unknown', what='An experimental utility.', readme=''))
        self.assertFalse(guide['capabilities'])
        self.assertEqual(guide['source'], '作者简介')
        self.assertIn('暂未', project_guide({})['note'])

    def test_unsupported_features_and_code_blocks_are_not_capabilities(self):
        guide = project_guide(dict(kind='app', readme='Vision is not supported.\n```\nagent tool use RAG\n```\n不支持语音转写。'))
        self.assertFalse(guide['capabilities'])

    def test_chinese_description_remains_readable_without_markdown(self):
        guide = project_guide(dict(kind='app', what='**这是一个管理个人知识和笔记的应用。**', readme='支持笔记和知识库。'))
        self.assertEqual(guide['summary'], '这是一个管理个人知识和笔记的应用。')
        self.assertEqual(len(guide['capabilities']), 1)


if __name__ == '__main__': unittest.main()

import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'desktop'))
from discovery import Discovery


def repo(name, topic='notes', stars=100):
    return dict(full_name=name, description=topic, topics=[topic], stars=stars, lang='Python', html_url='https://github.com/' + name)


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.store = {'favs': []}
        self.model = Discovery(self.store)

    def test_recent_search_changes_ranking(self):
        notes, agents = repo('a/notes'), repo('b/agents', 'agents')
        self.model.observe('记笔记', {'keywords': [{'term': 'notes'}]}, [notes])
        self.model.observe('AI 工作流', {'keywords': [{'term': 'agents'}]}, [agents])
        self.assertEqual(self.model.recommend()[0]['full_name'], 'b/agents')
        self.assertIn('AI 工作流', self.model.recommend()[0]['recommend_reason'])

    def test_favorite_changes_interests_and_is_not_recommended_again(self):
        self.model.ingest([repo('a/favorite', 'agents'), repo('b/similar', 'agents'), repo('c/other', 'notes', 10000)])
        self.store['favs'] = [{'full_name': 'a/favorite'}]
        rows = self.model.recommend()
        self.assertEqual(rows[0]['full_name'], 'b/similar')
        self.assertNotIn('a/favorite', [r['full_name'] for r in rows])

    def test_rotate_has_no_overlap_when_pool_is_large_enough(self):
        self.model.ingest([repo(f'a/project-{i}') for i in range(14)])
        first = {r['full_name'] for r in self.model.recommend()}
        second = {r['full_name'] for r in self.model.recommend(rotate=True)}
        self.assertFalse(first & second)

    def test_dismiss_and_preferences_survive_reload(self):
        self.model.ingest([repo('a/hidden'), repo('a/keep')])
        self.model.dismiss('a/hidden')
        loaded = Discovery(self.store)
        self.assertEqual([r['full_name'] for r in loaded.recommend()], ['a/keep'])

    def test_manual_direction_does_not_get_overridden_by_old_interests(self):
        self.model.observe('笔记', {'keywords': [{'term': 'notes'}]}, [repo('a/notes')])
        self.model.ingest([repo('a/agents', 'agents')], '探索方向 · ai-agents')
        self.assertEqual(self.model.recommend(topic='ai-agents')[0]['full_name'], 'a/agents')

    def test_empty_and_small_pools_are_safe_and_bounded(self):
        self.assertEqual(self.model.recommend(rotate=True), [])
        self.model.ingest([repo(f'a/{i}') for i in range(350)])
        self.assertEqual(len(self.model.data['pool']), 300)
        self.assertEqual(len(self.model.recommend()), 6)

    def test_reset_preserves_collections(self):
        self.store['favs'] = [{'full_name': 'a/favorite', 'topics': ['notes']}]
        self.model.observe('query', {}, [repo('a/sample')]); self.model.dismiss('a/sample')
        self.model.reset()
        self.assertEqual(self.model.data['searches'], [])
        self.assertEqual(self.model.data['hidden'], [])
        self.assertEqual(len(self.store['favs']), 1)

    def test_trending_sync_preserves_known_topics_and_license(self):
        self.model.ingest([{**repo('a/app'), 'license':'MIT'}])
        self.model.ingest([dict(full_name='a/app', stars=500, description='Notes app')], 'GitHub 日榜')
        self.assertEqual(self.model.data['pool']['a/app']['topics'], ['notes'])
        self.assertEqual(self.model.data['pool']['a/app']['license'], 'MIT')

    def test_personal_trending_reorders_candidates_without_changing_source_rank(self):
        self.model.observe('agents', {'keywords':[{'term':'agents'}]}, [])
        rows=[{**repo('a/notes'), 'trending_rank':1}, {**repo('b/agents','agents'), 'trending_rank':2}]
        self.assertEqual(self.model.rank_trending(rows)[0]['full_name'],'a/notes')
        personal=self.model.rank_trending(rows,True)
        self.assertEqual(personal[0]['full_name'],'b/agents')
        self.assertEqual(personal[0]['trending_rank'],2)

if __name__ == '__main__': unittest.main()

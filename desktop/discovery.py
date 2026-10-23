"""Local, explainable recommendations. No remote behavioural profile."""
import math
import time

FIELDS = ('full_name', 'owner', 'html_url', 'description', 'stars', 'forks', 'issues', 'lang',
          'license', 'size', 'topics', 'pushed_at', 'created_at', 'archived', 'avatar')


class Discovery:
    def __init__(self, store):
        self.store = store
        self.data = store.setdefault('discovery', {})
        self.data.setdefault('pool', {})
        self.data.setdefault('searches', [])
        self.data.setdefault('hidden', [])
        self.previous = []
        self.round = 0

    def ingest(self, repos, source='GitHub 探索', query=''):
        for repo in repos:
            name = repo.get('full_name')
            if not name or repo.get('archived'): continue
            old = self.data['pool'].get(name, {})
            item = {k: repo.get(k, old.get(k)) for k in FIELDS}
            item.update(source=source, seen_at=time.time(), origin_query=query or old.get('origin_query', ''))
            self.data['pool'][name] = item
        ordered = sorted(self.data['pool'].items(), key=lambda kv: kv[1].get('seen_at', 0), reverse=True)
        self.data['pool'] = dict(ordered[:300])

    def observe(self, query, plan, repos):
        terms = [k['term'] for k in (plan or {}).get('keywords', []) if k.get('term')][:6]
        terms += (plan or {}).get('topics', [])[:4]
        history = [h for h in self.data['searches'] if h['query'] != query]
        history.insert(0, dict(query=query, terms=list(dict.fromkeys(terms)), at=time.time()))
        self.data['searches'] = history[:12]
        self.ingest(repos, '来自你的搜索', query)
        self.previous = []

    def interests(self):
        weights = {}
        for i, item in enumerate(self.data['searches']):
            decay = 0.72 ** i
            for term in item['terms']:
                weights[term] = weights.get(term, 0) + 3 * decay
        for fav in self.store.get('favs', []):
            repo = self.data['pool'].get(fav['full_name'], fav)
            for term in (repo.get('topics') or [])[:6]:
                weights[term] = weights.get(term, 0) + 4
            if repo.get('lang'):
                term = repo['lang'].lower()
                weights[term] = weights.get(term, 0) + 1.5
        return weights

    def rank_trending(self, repos, personalized=False):
        weights = self.interests()
        rows = []
        for repo in repos:
            item = {**repo}
            metadata = {**self.data['pool'].get(repo['full_name'], {}), **repo}
            hay = ' '.join([repo['full_name'], repo.get('description') or '', metadata.get('lang') or '', ' '.join(metadata.get('topics') or [])]).lower()
            hits = [term for term in weights if term.lower() in hay]
            item['_interest_score'] = sum(weights[t] for t in hits)
            item['interest_reason'] = '匹配兴趣 · ' + ' / '.join(sorted(hits, key=weights.get, reverse=True)[:2]) if hits else '探索新方向'
            rows.append(item)
        if personalized: rows.sort(key=lambda r: (-r['_interest_score'], r.get('trending_rank', 999)))
        return rows

    def dismiss(self, name):
        self.data['hidden'] = list(dict.fromkeys([*self.data['hidden'], name]))[-500:]

    def reset(self):
        self.data['searches'] = []
        self.data['hidden'] = []
        self.previous = []

    def recommend(self, count=6, rotate=False, topic=''):
        weights = self.interests()
        hidden = set(self.data['hidden'])
        favorites = {f['full_name'] for f in self.store.get('favs', [])}
        rows = []
        for name, repo in self.data['pool'].items():
            if name in hidden or name in favorites or repo.get('archived'): continue
            hay = ' '.join([name, repo.get('description') or '', ' '.join(repo.get('topics') or []), repo.get('lang') or '']).lower()
            if topic and topic.lower() not in hay and repo.get('source') != '探索方向 · ' + topic:
                continue
            hits = [t for t in weights if t.lower() in hay]
            score = sum(weights[t] for t in hits) + min(math.log10(1 + (repo.get('stars') or 0)), 5) * .12
            recent = self.data['searches'][0] if self.data['searches'] else None
            if recent and repo.get('origin_query') == recent['query']:
                score += 5
                reason = '因为你搜索了「' + recent['query'][:22] + '」'
            elif hits:
                reason = '匹配你的兴趣 · ' + ' / '.join(sorted(hits, key=lambda t: weights[t], reverse=True)[:2])
            else:
                reason = repo.get('source') or '探索新方向'
            rows.append({**repo, 'recommend_reason': reason, '_rank': score})
        rows.sort(key=lambda r: (-r['_rank'], r['full_name']))
        if rotate:
            old = set(self.previous)
            rows = [r for r in rows if r['full_name'] not in old] + [r for r in rows if r['full_name'] in old]
            self.round += 1
        batch = rows[:count]
        self.previous = [r['full_name'] for r in batch]
        return batch

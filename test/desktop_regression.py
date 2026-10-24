"""Offline UI integration tests. Local fixtures never use the user's token."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['GHF_DISABLE_DISCOVERY'] = '1'
os.environ['GHF_DISABLE_INTRO'] = '1'
TEMP = tempfile.TemporaryDirectory()
os.environ['GHF_DATA_DIR'] = TEMP.name
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'desktop'))

REPO = dict(full_name='example/notes', owner='example', html_url='https://github.com/example/notes',
    description='Self-hosted notes with backlinks · 双向链接与本地笔记', stars=1200, forks=32, issues=8,
    lang='TypeScript', license='MIT', size=1024, topics=['note-taking', 'backlinks', 'self-hosted'],
    pushed_at='2026-10-20T10:00:00Z', created_at='2024-01-01T00:00:00Z', score=.82,
    primaryHit=1, health=.6, sources=['精确'], why=dict(matched=['note-taking', 'backlinks'], topicHits=[]))
PLAN = dict(primary='note-taking', keywords=[dict(term='note-taking', role='primary')],
    variants=[dict(id='v1', label='精确', q='note-taking backlinks', kind='exact')])
BRIEF = {**REPO, 'what': '管理个人知识与双向链接笔记。此页面为离线验收样例。', 'kind': 'app',
    'kindHint': '自托管应用；运行条件需要核对', 'fit': {'level': 'maybe', 'reasons': ['已找到项目声明的安装方式；尚未验证运行环境。']},
    'needs': ['需要 Docker 服务运行', '要自己申请 API key'], 'stack': ['TypeScript', 'Docker Compose'],
    'files': ['compose.yml', 'package.json'], 'steps': ['查看项目的配置说明。'],
    'commands': ['docker compose config --quiet', 'docker compose up -d'],
    'deploy': {'mode': 'compose', 'script': '@echo off\r\necho deployment-fixture\r\nexit /b 17', 'notes': ['示例脚本，仅用于界面验收']}}
MODELS = ['fixture/chinese-model']
CHAT_REQUESTS = []
CLOUD_STATUS = [200]
TRENDING_STATUS = [200]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        if self.path.startswith('/release-fixture.exe'):
            self.send_response(200); self.end_headers(); self.wfile.write(b'MZ-offline-release-fixture'); return
        if self.path.startswith('/api/tags'):
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({'models':[{'name':n} for n in MODELS]}).encode()); return
        if self.path.startswith('/api/trending'):
            if TRENDING_STATUS[0] != 200:
                self.send_response(503); self.end_headers(); self.wfile.write('{"error":"连接 GitHub 超时，请检查网络或系统代理是否可用"}'.encode()); return
            from urllib.parse import parse_qs, urlparse
            period = parse_qs(urlparse(self.path).query).get('period', ['daily'])[0]
            rows = [{**REPO, 'full_name': f'example/{period}-{i}', 'trending_rank':i+1, 'trending_period':period, 'stars_period':100-i} for i in range(10)]
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({'items':rows, 'period':period, 'fetchedAt':int(time.time()*1000), 'sourceUrl':'https://github.com/trending?since='+period}).encode()); return
        if self.path.startswith('/api/health'):
            body = json.dumps({'ok': True, 'app': 'idea-search', 'version': '2.8.2', 'quota': {}}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body); return
        if self.path.startswith('/api/discover'):
            if 'network-error' in self.path:
                self.send_response(503); self.end_headers(); self.wfile.write(b'{"error":"fixture unavailable"}'); return
            rows = [{**REPO, 'full_name': f'example/project-{i}', 'description': 'Self-hosted notes and a local-first knowledge base', 'stars': 200+i*100} for i in range(14)]
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({'items': rows}).encode()); return
        if self.path.startswith('/api/suggest'):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"items":[]}'); return
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
        if self.path.startswith('/api/analyze'):
            events = [{'type': 'stage', 'name': '读取 README'}, {'type': 'done', 'data': BRIEF}]
        else:
            events = [{'type': 'plan', 'plan': PLAN}, {'type': 'done', 'plan': PLAN, 'results': [REPO],
                'native': [], 'stats': {'candidates': 1, 'afterDedupe': 1, 'afterFilter': 1}, 'warnings': []}]
        try:
            for event in events:
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode()); self.wfile.flush()
                time.sleep(.15)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        CHAT_REQUESTS.append(data)
        cloud = self.path == '/chat/completions'
        if cloud and CLOUD_STATUS[0] != 200:
            self.send_response(CLOUD_STATUS[0]); self.end_headers(); self.wfile.write(b'{"error":{"message":"fixture rejected"}}'); return
        if data.get('format') == 'json' or data.get('response_format'):
            rows = json.loads(data['messages'][-1]['content'])
            content = json.dumps({r['id']:'帮助开发者整理资料并探索实用工具，支持根据任务选择合适的使用方式。' for r in rows})
            body = json.dumps({'choices':[{'message':{'content':content}}]} if cloud else {'message':{'content':content}})
        else:
            content = '适合想把模型接入工作流的开发者。\n场景一：输入一份资料和问题 → 参考示例构建有资料依据的回答。\n场景二：输入待处理任务 → 参考函数调用案例连接外部工具。\n第一次可以先选一个案例，核对依赖和 API key。'
            body = ('data: ' + json.dumps({'choices':[{'delta':{'content':content}}]}) + '\n\ndata: [DONE]\n\n') if cloud else json.dumps({'message':{'content':content}, 'done':True}) + '\n'
        self.send_response(200); self.end_headers(); self.wfile.write(body.encode())

SERVER = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
os.environ['GHF_PORT'] = str(SERVER.server_port)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
from PySide6.QtCore import QProcess, QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QLabel
from PySide6.QtGui import QFontDatabase
from run import build_app
from ui import MainWindow
from env import check_needs
from assistant import ChatWorker
from client import StreamWorker
import assistant
import introductions
assistant.OLLAMA = introductions.OLLAMA = f'http://127.0.0.1:{SERVER.server_port}'
APP = build_app()
for filename in ('msyh.ttc', 'segoeui.ttf'):
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename
    if font.exists(): QFontDatabase.addApplicationFont(str(font))

class EngineStub:
    def stop(self): pass

def pump(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate(): return True
        time.sleep(.01)
    return False

class DesktopTests(unittest.TestCase):
    def setUp(self):
        CLOUD_STATUS[0] = 200
        MODELS[:] = ['fixture/chinese-model']; CHAT_REQUESTS.clear()
        (Path(TEMP.name) / '.github-finder-desktop.json').write_text('{"history":[],"favs":[]}', 'utf-8')
        self.win = MainWindow(EngineStub())
        self.win.show()
        APP.processEvents()

    def tearDown(self):
        self.win.close(); self.win.deleteLater(); APP.processEvents()

    def test_navigation_search_and_deployment_output(self):
        shots = ROOT / 'artifacts' / 'ui'; shots.mkdir(parents=True, exist_ok=True)
        self.win.grab().save(str(shots / 'home.png'))
        self.win.search.setText('自托管的笔记，支持双链')
        self.win.do_search()
        self.assertTrue(pump(lambda: self.win.last_done))
        self.assertEqual(len(self.win.items), 1)
        self.assertTrue(self.win.search_toolbar.isVisible())
        self.assertTrue(self.win.status.isVisible())
        self.assertFalse(self.win.plan_frame.isVisible())
        pump(lambda: False, .25)
        self.win.grab().save(str(shots / 'search.png'))
        self.win.open_detail(REPO)
        page = self.win.detail_page
        self.assertTrue(pump(lambda: page.data is not None))
        self.assertFalse(page.isWindow())
        self.assertEqual(len([w for w in APP.topLevelWidgets() if w.isVisible()]), 1)
        pump(lambda: False, .25)
        self.win.grab().save(str(shots / 'detail.png'))
        # Test only a harmless local fixture; no package installation or external repository.
        import detail
        detail.DEPLOY_DIR = Path(TEMP.name) / 'deploy'
        page.deploy_review.setChecked(True)
        page.run_deploy()
        self.assertTrue(pump(lambda: page.deploy_process.state() == QProcess.NotRunning))
        self.assertIn('deployment-fixture', page.terminal.toPlainText())
        self.assertIn('17', page.footer.text())
        self.win.back_to_search()
        self.assertEqual(len(self.win.items), 1)
        self.assertEqual(self.win.pages.count(), 1)

    def test_cancel_and_close_active_requests(self):
        self.win.search.setText('笔记')
        self.win.do_search()
        self.win.search_or_cancel()
        self.assertFalse(self.win.worker.isRunning())
        self.assertIn('取消', self.win.status.text())
        self.win.do_search()
        self.win.open_detail(REPO)
        self.win.close()
        self.assertFalse(self.win.worker.isRunning())

    def test_small_sse_event_arrives_before_stream_ends(self):
        worker = StreamWorker(f'http://127.0.0.1:{SERVER.server_port}/api/stream', self.win)
        events = []
        worker.event.connect(events.append)
        worker.start()
        self.assertTrue(pump(lambda: bool(events), .14))
        self.assertEqual(events[0]['type'], 'plan')
        worker.stop()

    def test_discovery_refresh_rotate_dismiss_favorite_and_compare(self):
        self.win.fetch_recommendations('note-taking')
        self.assertTrue(pump(lambda: self.win.discovery_reply is None))
        self.assertEqual(len(self.win.recommendations), 6)
        self.win.navigate('home')
        before = {r['full_name'] for r in self.win.recommendations}
        self.win.rotate_recommendations()
        self.assertFalse(before & {r['full_name'] for r in self.win.recommendations})
        hidden = self.win.recommendations[0]['full_name']
        self.win.dismiss_project(hidden)
        self.assertNotIn(hidden, [r['full_name'] for r in self.win.recommendations])
        selected = self.win.recommendations[0]
        self.win.toggle_fav(selected)
        self.assertNotIn(selected['full_name'], [r['full_name'] for r in self.win.recommendations])
        pump(lambda: False, .2)
        shots = ROOT / 'artifacts' / 'ui'; shots.mkdir(parents=True, exist_ok=True)
        self.win.grab().save(str(shots / 'discovery.png'))
        for item in list(self.win.discovery.data['pool'].values())[:4]: self.win.toggle_compare(item)
        self.assertEqual(len(self.win.comparison), 3)
        self.win.navigate('compare')
        pump(lambda: False, .2)
        self.win.grab().save(str(shots / 'comparison.png'))
        self.win.copy_comparison()
        self.assertIn('| 项目 |', APP.clipboard().text())
        self.win.navigate('library')
        self.win.copy_library()
        self.assertIn(selected['full_name'], APP.clipboard().text())
        self.assertEqual(len(self.win.store['favs']), 1)

    def test_saved_search_restores_filters_and_new_search_updates_recommendations(self):
        self.win.search.setText('本地笔记')
        self.win.sp_stars.setValue(500)
        self.win.chk_license.setChecked(True)
        self.win.save_query()
        self.assertEqual(len(self.win.saved_queries), 1)
        self.win.sp_stars.setValue(0)
        self.win.restore_query(self.win.saved_queries[0])
        self.assertTrue(pump(lambda: self.win.last_done))
        self.assertEqual(self.win.sp_stars.value(), 500)
        self.assertTrue(self.win.chk_license.isChecked())
        self.assertEqual(self.win.discovery.data['searches'][0]['query'], '本地笔记')
        self.assertTrue(self.win.recommendations)
        self.assertEqual(self.win.view_mode, 'results')

    def test_favorite_click_preserves_scroll_in_discovery_results_and_library(self):
        rows = [{**REPO, 'full_name': f'example/scroll-{i}'} for i in range(40)]
        self.win.discovery.ingest(rows)
        self.win.items = {r['full_name']: r for r in rows}
        self.win.resize(1180, 760)
        for mode in ('home', 'results', 'library'):
            with self.subTest(mode=mode):
                self.win.store['favs'] = [] if mode != 'library' else [
                    {**r, 'url': r['html_url'], 'desc': r['description']} for r in rows]
                self.win.navigate(mode)
                pump(lambda: False, .3)
                bar = self.win.scroll.verticalScrollBar()
                self.assertGreater(bar.maximum(), 100)
                bar.setValue(bar.maximum() // 2)
                buttons = [b for b in self.win.host.findChildren(QPushButton)
                    if (b.objectName() == 'star' or b.text() in ('收藏', '已收藏'))
                    and 0 <= b.mapTo(self.win.scroll.viewport(), QPoint(0, 0)).y()
                    < self.win.scroll.viewport().height() - b.height()]
                self.assertTrue(buttons)
                button = buttons[0]
                button.setFocus()
                APP.processEvents()
                before = bar.value()
                count = len(self.win.store['favs'])
                button.click()
                pump(lambda: False, .3)
                self.assertEqual(bar.value(), min(before, bar.maximum()))
                self.assertEqual(len(self.win.store['favs']), count + (-1 if mode == 'library' else 1))

    def test_discovery_topic_switch_cancels_stale_request_and_failure_preserves_cards(self):
        self.win.select_topic('ai-agents')
        self.win.select_topic('productivity')
        self.assertTrue(pump(lambda: self.win.discovery_reply is None))
        self.assertEqual(len(self.win.recommendations), 6)
        self.assertTrue(all(r['source'] == '探索方向 · productivity' for r in self.win.recommendations))
        before = [r['full_name'] for r in self.win.recommendations]
        self.win.fetch_recommendations('network-error')
        self.assertTrue(pump(lambda: self.win.discovery_reply is None))
        self.assertEqual(before, [r['full_name'] for r in self.win.recommendations])
        self.assertIn('更新失败', self.win.discovery_message)

    def test_trending_failure_keeps_snapshot_and_retry_recovers(self):
        self.win.navigate('trending')
        self.assertTrue(pump(lambda: self.win.trending_reply is None))
        self.assertFalse(self.win.search_toolbar.isVisible())
        self.assertFalse(self.win.filter_panel.isVisible())
        self.assertFalse(self.win.status.isVisible())
        before = self.win.trending_snapshots[self.win.trending_period]
        try:
            TRENDING_STATUS[0] = 503
            self.win.fetch_trending(True)
            self.assertTrue(pump(lambda: self.win.trending_reply is None))
            self.assertEqual(self.win.trending_snapshots[self.win.trending_period], before)
            self.assertEqual(len(self.win.trending_visible), 10)
            self.assertIn('保留上次快照', self.win.trending_status)
        finally: TRENDING_STATUS[0] = 200
        self.win.fetch_trending(True)
        self.assertTrue(pump(lambda: self.win.trending_reply is None))
        self.assertNotIn('失败', self.win.trending_status)
        self.win.search.setText('notes')
        self.win.do_search()
        self.assertTrue(pump(lambda: self.win.last_done))
        self.assertTrue(self.win.search_toolbar.isVisible())

    def test_unknown_environment_is_not_success(self):
        rows = check_needs({'tools': {'docker': 'installed'}}, ['需要 Docker 服务运行', 'API key', '数据库', 'CUDA 显卡'])
        self.assertTrue(all(r['ok'] is None for r in rows))
        worker = ChatWorker('我电脑能跑吗', {}, '')
        self.assertIn('不能保证', worker.rule_answer('我电脑能跑吗'))

    def test_project_question_uses_ai_scenarios_and_examples_do_not_get_generic_start_commands(self):
        self.win.open_detail(REPO)
        page = self.win.detail_page
        self.assertTrue(pump(lambda: page.data is not None))
        data = {**BRIEF, 'kind': 'examples', 'what': 'Code examples for developers.',
            'readme': '# Cookbook\n\n## Tool use\nFunction calling examples.\n## RAG\nRetrieval augmented generation.',
            'commands': [], 'deploy': {'script': ''}, 'dirs': ['tool_use', 'capabilities']}
        page.on_data(data)
        button = next(b for b in page.question_buttons if b.text() == '它能干什么？')
        button.click()
        self.assertTrue(pump(lambda: len(page.chat_history) == 2))
        self.assertIn('场景一', page.chat_history[-1]['content'])
        self.assertTrue(page.model_tag.text().startswith('AI ·'))
        self.assertTrue(CHAT_REQUESTS)
        self.assertIn('不要复述', CHAT_REQUESTS[-1]['messages'][0]['content'])
        self.assertNotIn(data['what'], page.chat_history[-1]['content'])
        page.ask('他能干什么')
        self.assertTrue(pump(lambda: len(page.chat_history) == 4))
        self.assertNotIn('换个问法', page.chat_history[-1]['content'])
        worker = ChatWorker('怎么启动？', data, '')
        self.assertIn('案例', worker.rule_answer('怎么启动？'))
        self.assertNotIn('setup.py', worker.rule_answer('怎么启动？'))
        self.assertIn('尚未确认统一', worker.rule_answer('端口多少？'))
        page.ask('怎么开始？')
        self.assertTrue(pump(lambda: len(page.chat_history) == 6))
        self.assertIn('tool_use', page.chat_history[-1]['content'])
        pump(lambda: False, .15)
        page.grab().save(str(ROOT / 'artifacts' / 'ui' / 'project-guide.png'))
        self.win.resize(1180, 760)
        pump(lambda: False, .2)
        self.assertEqual(page.content_splitter.orientation(), Qt.Vertical)
        self.assertTrue(page.chat_input.isVisible())
        self.assertGreater(page.scroll.height(), 100)
        page.ask('它有什么功能？')
        self.assertTrue(pump(lambda: len(page.chat_history) == 8))
        pump(lambda: False, .1)
        transcript_bar = page.transcript.verticalScrollBar()
        self.assertLessEqual(transcript_bar.maximum() - transcript_bar.value(), 2)
        page.grab().save(str(ROOT / 'artifacts' / 'ui' / 'project-guide-narrow.png'))

    def test_missing_ai_does_not_copy_author_text_as_an_answer(self):
        MODELS.clear()
        worker = ChatWorker('他能干什么', {'what':'DO NOT COPY AUTHOR TEXT'}, '')
        responses=[]; worker.finished_text.connect(responses.append); worker.start()
        self.assertTrue(pump(lambda: bool(responses)))
        self.assertIn('AI 暂时不可用', responses[0]); self.assertNotIn('DO NOT COPY', responses[0])

    def test_chinese_introduction_updates_existing_label_without_rebuilding_or_scrolling(self):
        os.environ['GHF_DISABLE_INTRO'] = '0'
        try:
            self.win.items={f'example/intro-{i}':{**REPO,'full_name':f'example/intro-{i}', 'description':'Self-hosted notes with backlinks and a local-first knowledge base.'} for i in range(25)}
            self.win.navigate('results')
            bar=self.win.scroll.verticalScrollBar(); pump(lambda: False,.1); bar.setValue(150)
            before=bar.value()
            label=self.win.host.findChildren(QPushButton, 'star')[0]
            self.assertTrue(pump(lambda: bool(self.win.intro_service.cache), 5))
            self.assertTrue(label.isVisible())
            self.assertEqual(before,bar.value())
            self.assertTrue(any('本机 AI' in w.toolTip() for w in self.win.host.findChildren(QLabel, 'chineseIntro')))
            self.assertTrue(pump(lambda: len(self.win.intro_service.cache) >= 25, 8))
            self.assertEqual(before,bar.value())
        finally: os.environ['GHF_DISABLE_INTRO']='1'

    def test_trending_periods_keep_github_rank_and_support_interest_ordering(self):
        self.win.navigate('trending')
        self.assertTrue(pump(lambda: self.win.trending_reply is None))
        self.assertEqual(self.win.trending_visible[0]['full_name'], 'example/daily-0')
        self.win.select_trending_period('weekly'); self.win.select_trending_period('monthly')
        self.assertTrue(pump(lambda: self.win.trending_reply is None))
        self.assertTrue(all(r['trending_period']=='monthly' for r in self.win.trending_visible))
        self.win.discovery.observe('monthly-8', {'keywords':[{'term':'monthly-8'}]}, [])
        self.win.personalize_trending(True)
        self.assertEqual(self.win.trending_visible[0]['full_name'],'example/monthly-8')
        self.assertEqual(self.win.trending_visible[0]['trending_rank'],9)
        self.win.grab().save(str(ROOT/'artifacts'/'ui'/'trending.png'))

    def test_deepseek_uses_bearer_and_sse_and_reports_invalid_keys(self):
        from unittest.mock import patch
        configuration = dict(provider='deepseek', base_url=f'http://127.0.0.1:{SERVER.server_port}', key='sk-fixture-not-secret', model='fixture-deepseek')
        with patch('assistant.cloud_config', return_value=configuration):
            worker=ChatWorker('它能干什么', BRIEF, 'PRIVATE-HARDWARE-MARKER', settings={'ai_provider':'deepseek'})
            answers=[]; worker.finished_text.connect(answers.append); worker.start()
            self.assertTrue(pump(lambda: bool(answers)))
            self.assertIn('场景一',answers[0])
            self.assertNotIn('PRIVATE-HARDWARE-MARKER',CHAT_REQUESTS[-1]['messages'][0]['content'])
            self.assertEqual(CHAT_REQUESTS[-1]['model'],'fixture-deepseek')
            CLOUD_STATUS[0]=401
            rejected=ChatWorker('它能干什么', BRIEF, '', settings={'ai_provider':'deepseek'})
            failures=[]; rejected.finished_text.connect(failures.append); rejected.start()
            self.assertTrue(pump(lambda:bool(failures)))
            self.assertIn('API Key 无效',failures[0])

    def test_recommended_launch_executes_environment_fixture_in_app(self):
        self.win.open_detail(REPO); page=self.win.detail_page
        self.assertTrue(pump(lambda:page.data is not None))
        data={**BRIEF,'launch':dict(mode='environment',title='准备开发环境',button='一键安装开发环境',description='离线安装流程样例')}
        page.on_data(data)
        import detail
        detail.DEPLOY_DIR=Path(TEMP.name)/'deploy-route'
        page.launch_button.click()
        self.assertTrue(pump(lambda:page.deploy_process and page.deploy_process.state()==QProcess.NotRunning))
        self.assertIn('deployment-fixture',page.terminal.toPlainText())

    def test_release_download_checks_digest_without_running_any_program(self):
        import hashlib
        from unittest.mock import patch
        from release_install import ReleaseDownload
        payload=b'MZ-offline-release-fixture'
        asset=dict(name='fixture.exe',url='https://github.com/example/app/releases/download/v1/fixture.exe',digest='sha256:'+hashlib.sha256(payload).hexdigest())
        job=ReleaseDownload(asset,'example/app',Path(TEMP.name)/'downloads',self.win)
        request_get=job.nam.get
        from PySide6.QtNetwork import QNetworkRequest
        from PySide6.QtCore import QUrl
        paths=[];errors=[];job.ready.connect(paths.append);job.failed.connect(errors.append)
        with patch.object(job.nam,'get',side_effect=lambda request:request_get(QNetworkRequest(QUrl(f'http://127.0.0.1:{SERVER.server_port}/release-fixture.exe')))):
            job.start();self.assertTrue(pump(lambda:bool(paths or errors)))
        self.assertFalse(errors); self.assertEqual(Path(paths[0]).read_bytes(),payload)
        bad=ReleaseDownload({**asset,'digest':'sha256:'+'0'*64},'example/app',Path(TEMP.name)/'bad-downloads',self.win)
        get_bad=bad.nam.get;failures=[];bad.failed.connect(failures.append)
        with patch.object(bad.nam,'get',side_effect=lambda request:get_bad(QNetworkRequest(QUrl(f'http://127.0.0.1:{SERVER.server_port}/release-fixture.exe')))):
            bad.start();self.assertTrue(pump(lambda:bool(failures)))
        self.assertIn('校验值',failures[0]);self.assertFalse(bad.path.exists())

    def test_switching_ai_provider_does_not_replace_deepseek_model_with_stale_local_results(self):
        from unittest.mock import patch
        from ai_support import AISettings
        with patch('ai_support.OLLAMA',f'http://127.0.0.1:{SERVER.server_port}'):
            dialog=AISettings(self.win.store,self.win)
            dialog.provider.setCurrentIndex(1)
            dialog.show();pump(lambda:False,.15)
            self.assertEqual(dialog.models.currentText(),'deepseek-flash')
            self.assertTrue(dialog.key.isVisible())
            dialog.grab().save(str(ROOT/'artifacts'/'ui'/'deepseek-settings.png'))
            dialog.close();dialog.deleteLater()

if __name__ == '__main__':
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DesktopTests))
    finally: SERVER.shutdown()
    raise SystemExit(0 if result.wasSuccessful() else 1)

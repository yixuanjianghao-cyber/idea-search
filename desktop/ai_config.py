"""AI settings and per-Windows-user encrypted API key storage."""
import base64
import ctypes
import json
import os
from pathlib import Path
from urllib.parse import urlparse

KEY_FILE = Path(os.environ.get('GHF_DATA_DIR') or Path.home()) / '.github-finder-ai-key.json'


class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != 'nt': raise RuntimeError('当前密钥保护功能需要 Windows')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt32.CryptProtectData(ctypes.byref(source), 'IdeaSearch AI key', None, None, None, 1, ctypes.byref(target))
    if not ok: raise ctypes.WinError(ctypes.get_last_error())
    try: return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def save_api_key(key):
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    encrypted = base64.b64encode(_crypt(key.encode())).decode() if key else ''
    temporary = KEY_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps({'deepseek':encrypted}), encoding='utf-8')
    temporary.replace(KEY_FILE)


def load_api_key():
    if os.environ.get('DEEPSEEK_API_KEY'): return os.environ['DEEPSEEK_API_KEY']
    try:
        encrypted = json.loads(KEY_FILE.read_text(encoding='utf-8')).get('deepseek')
        return _crypt(base64.b64decode(encrypted), True).decode() if encrypted else ''
    except Exception: return ''


def cloud_config(store):
    provider = store.get('ai_provider', 'ollama')
    base = store.get('ai_base_url') or 'https://api.deepseek.com'
    parsed = urlparse(base)
    if provider == 'deepseek' and (parsed.scheme != 'https' or parsed.hostname != 'api.deepseek.com' or parsed.username or parsed.password):
        raise ValueError('DeepSeek 地址应为 https://api.deepseek.com 或 https://api.deepseek.com/v1')
    path = parsed.path.rstrip('/')
    if path not in ('', '/v1') or parsed.query or parsed.fragment: raise ValueError('API 地址只填基础地址，不要带 /chat/completions、参数或锚点')
    return dict(provider=provider, base_url=base.rstrip('/'), model=store.get('ai_cloud_model') or 'deepseek-flash', key=load_api_key())


def api_error(status, message=''):
    return {
        401:'API Key 无效或已过期，请到 AI 设置检查 DeepSeek 密钥。',
        402:'DeepSeek 账户余额不足，请在 DeepSeek 平台检查余额。',
        403:'当前账号或模型没有访问权限。',
        404:'接口地址或模型名称不存在，请检查基础地址和模型。',
        429:'请求过于频繁，稍后重试。',
    }.get(status, 'AI 服务连接失败，请检查网络、基础地址和模型。')

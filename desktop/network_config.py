"""Pass the user's configured proxy to Node; keep local engine traffic local."""
import os
import urllib.request


def engine_environment(source=None, proxies=None):
    env = dict(os.environ if source is None else source)
    if proxies is None:
        # getproxies() returns early when *only* NO_PROXY exists, hiding the
        # Windows registry proxy. Merge the sources explicitly on Windows.
        registry = getattr(urllib.request, 'getproxies_registry', lambda: {})()
        configured = {**registry, **urllib.request.getproxies_environment()}
    else:
        configured = proxies
    for protocol in ('http', 'https'):
        key = protocol.upper() + '_PROXY'
        # Explicit environment settings take priority over Windows Internet Settings.
        if key not in env and key.lower() not in env:
            value = configured.get(protocol) or configured.get('all')
            if value and value.lower().startswith(('http://', 'https://')):
                env[key] = value
    env['NODE_USE_ENV_PROXY'] = '1'
    for key in ('NO_PROXY', 'no_proxy'):
        existing = env.get(key, env.get('NO_PROXY', env.get('no_proxy', '')))
        env[key] = ','.join(filter(None, [existing, 'localhost', '127.0.0.1', '[::1]']))
    return env

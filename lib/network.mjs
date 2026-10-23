// Retry only reads and transient transport errors. Never retry authentication or quotas.
export function networkMessage(error) {
  const codes = [error?.code, error?.cause?.code, ...(error?.cause?.errors || []).map(e => e.code)];
  if (error?.name === 'TimeoutError' || codes.some(c => /TIMEOUT|TIMEDOUT/.test(c || '')))
    return '连接 GitHub 超时，请检查网络或系统代理是否可用';
  if (codes.some(c => /CERT|TLS|SSL/.test(c || '')))
    return 'GitHub 安全连接验证失败，请检查系统时间及代理证书';
  if (codes.some(c => /ENOTFOUND|EAI_AGAIN/.test(c || '')))
    return '无法解析 GitHub 地址，请检查网络或 DNS';
  if (codes.includes('ECONNREFUSED')) return '连接被拒绝，请检查网络及系统代理是否已启动';
  if (error?.message === 'fetch failed' || codes.some(c => /ECONNRESET|UND_ERR_SOCKET/.test(c || '')))
    return '与 GitHub 的连接中断，请检查网络或系统代理后重试';
  return error?.message || 'GitHub 连接失败，请稍后重试';
}

export async function fetchRead(url, options = {}, timeout = 20000) {
  const deadline = Date.now() + timeout;
  for (let attempt = 0; attempt < 2; attempt++) {
    let response;
    try {
      const remaining = Math.max(1, deadline - Date.now());
      const signal = AbortSignal.timeout(Math.min(remaining, attempt ? timeout : Math.ceil(timeout / 2)));
      response = await fetch(url, {...options, signal:options.signal ? AbortSignal.any([options.signal, signal]) : signal});
      if (!attempt && [502, 503, 504].includes(response.status)) {
        await response.body?.cancel();
      } else return response;
    } catch (error) {
      if (options.signal?.aborted) throw error;
      const message = networkMessage(error);
      const certificateError = /证书|安全连接/.test(message);
      if (attempt || certificateError || Date.now() >= deadline) {
        throw new Error(message, {cause:error});
      }
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}

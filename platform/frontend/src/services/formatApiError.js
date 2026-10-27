// Turn an axios error into readable text. Handles FastAPI 422 (detail = array of
// {loc,msg}), HTTPException (detail = string), and falls back to the raw body /
// axios message so a failure is never shown as just "Request failed with status…".
export function formatApiError(e) {
  const d = e?.response?.data?.detail;
  if (Array.isArray(d)) {
    return d
      .map((x) => {
        const loc = (x.loc || []).filter((p) => p !== 'body').join('.');
        return loc ? `${loc}: ${x.msg}` : x.msg;
      })
      .join('; ');
  }
  if (typeof d === 'string') return d;
  if (d) return JSON.stringify(d);
  if (e?.response?.data) return JSON.stringify(e.response.data);
  return e?.message || 'Request failed';
}

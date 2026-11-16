// A node --test reporter for demos/check.py: one JSON line per finished test, and one per chunk a test file wrote
// to stderr (which says why a file that died before its tests did). Node's own reporters format for people and
// change between releases; this keeps to the documented event fields (type, data.name, data.nesting,
// data.details, data.message), which Node 22 and later share.
export default async function* reporter(source) {
  for await (const event of source) {
    if (event.type === 'test:stderr') {
      yield JSON.stringify({ demo_event: 'stderr', file: event.data.file || null, message: event.data.message }) + '\n';
      continue;
    }
    if (event.type !== 'test:pass' && event.type !== 'test:fail') continue;
    const data = event.data;
    const error = data.details && data.details.error;
    const cause = error && (error.cause || error);
    yield JSON.stringify({
      demo_event: 'test',
      ok: event.type === 'test:pass',
      name: data.name,
      nesting: data.nesting,
      kind: (data.details && data.details.type) || 'test',
      file: data.file || null,
      error: cause ? String(cause.message || cause) : null,
    }) + '\n';
  }
}

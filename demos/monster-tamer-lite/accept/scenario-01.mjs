// Item 1, the part that needs the workspace's code: what each file of the Layout list exports (each name and the
// typeof its value), and the exports of src/data.js that are fixed in value. Runs beside the workspace
// (demos/probe.mjs, scenario()) and returns what it saw; 01-layout.test.mjs compares. The files themselves
// (originality, assets, the page, main.js) are read as text by the test.

export async function run({ load }, files) {
  const modules = {};
  for (const file of files) {
    try {
      const mod = await load(file);
      modules[file] = { loadError: null, exports: Object.fromEntries(Object.keys(mod).map((n) => [n, typeof mod[n]])) };
    } catch (e) {
      modules[file] = { loadError: String(e && e.message), exports: {} };
    }
  }
  let data;
  try {
    const d = await load('src/data.js');
    data = { loadError: null, TYPES: structuredClone(d.TYPES), STATUS_TURNS: structuredClone(d.STATUS_TURNS), chartType: typeof d.TYPE_CHART };
  } catch (e) {
    data = { loadError: String(e && e.message) };
  }
  return { modules, data };
}

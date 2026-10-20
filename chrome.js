// Chrome tab verbs for mac-proxy: osascript -l JavaScript chrome.js VERB ARGS_JSON -> {running, result} | {error}
// Tab ids are numbers (JXA hands them back as strings). Never launches Chrome: when it isn't running, every verb answers {running: false, result: null}.
function okUrl(u) { return typeof u === 'string' && /^(https?:|about:blank$|chrome:\/\/newtab\/?$)/.test(u); }

function eachTab(chrome, fn) {
  for (const w of chrome.windows()) for (const t of w.tabs()) if (fn(w, t) === false) return;
}

const VERBS = {
  // [{id, url, title, window}] of every tab
  list_tabs(chrome) {
    const ids = chrome.windows.tabs.id(), urls = chrome.windows.tabs.url(), titles = chrome.windows.tabs.title();
    const out = [];
    ids.forEach((ws, i) => ws.forEach((id, j) => out.push({id: Number(id), url: urls[i][j], title: titles[i][j], window: i})));
    return out;
  },
  active_tab(chrome) {
    if (!chrome.windows.length) return null;
    const t = chrome.windows[0].activeTab;
    return {id: Number(t.id()), url: t.url(), title: t.title()};
  },
  close_tabs(chrome, a) {
    const want = new Set((a.ids || []).map(Number)), closed = [];
    eachTab(chrome, (w, t) => { if (want.has(Number(t.id()))) closed.push(Number(t.id())); });
    // close after the scan: closing shifts tab indexes
    for (const id of closed) {
      for (const w of chrome.windows()) { try { w.tabs.byId(String(id)).close(); break; } catch (e) {} }
    }
    return closed;
  },
  set_url(chrome, a) {
    if (!okUrl(a.url)) throw new Error('url not allowed: ' + a.url);
    let hit = false;
    eachTab(chrome, (w, t) => { if (Number(t.id()) === Number(a.id)) { t.url = a.url; hit = true; return false; } });
    return hit;
  },
  open_url(chrome, a) {
    if (!okUrl(a.url)) throw new Error('url not allowed: ' + a.url);
    if (!chrome.windows.length) chrome.Window().make();
    chrome.windows[0].tabs.push(chrome.Tab({url: a.url}));
    return {id: Number(chrome.windows[0].activeTab.id())};
  },
};

function run(argv) {
  const verb = VERBS[argv[0]];
  if (!verb) return JSON.stringify({error: 'unknown chrome verb: ' + argv[0]});
  const chrome = Application('Google Chrome');
  if (!chrome.running()) return JSON.stringify({running: false, result: null});
  try {
    return JSON.stringify({running: true, result: verb(chrome, JSON.parse(argv[1] || '{}'))});
  } catch (e) {
    return JSON.stringify({error: String(e.message || e)});
  }
}

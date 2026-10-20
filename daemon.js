// mac-proxy daemon (JXA). launchd runs it as /usr/bin/osascript, so every macOS privacy grant (Automation of
// Chrome/Finder/…, Screen Recording) is filed under that stable Apple-signed binary instead of under the current
// Claude Code version (~/.local/share/claude/versions/<ver>), which re-prompts after every update.
//
// Callers drop a JSON request {verb, args} in req/ and read {ok, result|error} from res/ (see mac_proxy.py).
// Each request runs as a child process with a timeout, so one hung script never stalls the others; children
// inherit this daemon as their "responsible process", so the grants still apply. Editing this file (or
// chrome.js) never re-prompts: the grants belong to /usr/bin/osascript.
ObjC.import('Foundation');

const ROOT = $.NSHomeDirectory().js + '/.mac-proxy';
const REQ = ROOT + '/req', RES = ROOT + '/res', TMP = ROOT + '/tmp';
const fm = $.NSFileManager.defaultManager;
const MAX_IDLE_LOOPS = 3000;         // ~10 min of polling, then exit when idle; launchd restarts (keeps memory flat)
// Frequent pings reset the idle counter, so also exit (between jobs) after an hour of uptime. 2026-10-11 the
// daemon had run 38 h and every `run` request hung with no child process left; a restart fixed it.
const MAX_UPTIME_S = 3600;
const STUCK_GRACE_S = 20;            // a job past its timeout + this is force-finished (NSTask state can go stale)
const RES_TTL_S = 300;
const DEFAULT_TIMEOUT_S = 60, MAX_TIMEOUT_S = 600;
const OSA = '/usr/bin/osascript';
const CHROME_VERBS = ['list_tabs', 'active_tab', 'close_tabs', 'set_url', 'open_url'];

function ls(dir) {
  const r = fm.contentsOfDirectoryAtPathError(dir, null);
  return r.isNil() ? [] : ObjC.deepUnwrap(r);
}
function readText(p) {
  const s = $.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null);
  return s.isNil() ? '' : s.js;
}
function writeText(p, s) { $(s).writeToFileAtomicallyEncodingError(p, true, $.NSUTF8StringEncoding, null); }
function rm(p) { fm.removeItemAtPathError(p, null); }
function ageS(p) {
  const a = fm.attributesOfItemAtPathError(p, null);
  return a.isNil() ? 0 : -a.fileModificationDate.timeIntervalSinceNow;
}

// request -> argv of the child to run (or throws)
function build(verb, a) {
  if (CHROME_VERBS.includes(verb)) return [OSA, '-l', 'JavaScript', ROOT + '/chrome.js', verb, JSON.stringify(a)];
  if (verb === 'applescript' || verb === 'jxa') {
    if (typeof a.script !== 'string' || !a.script) throw new Error('script is required');
    const argv = verb === 'jxa' ? [OSA, '-l', 'JavaScript', '-e', a.script] : [OSA, '-e', a.script];
    return argv.concat((a.argv || []).map(String));
  }
  if (verb === 'screenshot') {
    if (typeof a.path !== 'string' || !a.path.startsWith('/')) throw new Error('absolute path is required');
    return ['/usr/sbin/screencapture', '-x'].concat((a.options || []).map(String), [a.path]);
  }
  if (verb === 'run') {
    const argv = (a.argv || []).map(String);
    if (!argv.length) throw new Error('argv is required');
    return argv[0].startsWith('/') ? argv : ['/usr/bin/env'].concat(argv);
  }
  throw new Error('unknown verb: ' + verb);
}

function start(name, req) {
  const a = req.args || {};
  const timeout = Math.min(Math.max(Number(a.timeout) || DEFAULT_TIMEOUT_S, 1), MAX_TIMEOUT_S);
  const argv = build(req.verb, a);
  const out = TMP + '/' + name + '.out', err = TMP + '/' + name + '.err';
  for (const p of [out, err]) fm.createFileAtPathContentsAttributes(p, $(), $());
  const t = $.NSTask.alloc.init;
  t.launchPath = '/usr/bin/perl';     // alarm = per-request timeout, then exec the real command
  t.arguments = ['-e', 'alarm shift; exec @ARGV or die "exec $ARGV[0]: $!\\n"', String(timeout)].concat(argv);
  t.currentDirectoryPath = typeof a.cwd === 'string' && a.cwd ? a.cwd : $.NSHomeDirectory();
  t.standardInput = $.NSFileHandle.fileHandleWithNullDevice;
  t.standardOutput = $.NSFileHandle.fileHandleForWritingAtPath(out);
  t.standardError = $.NSFileHandle.fileHandleForWritingAtPath(err);
  t.launch;
  return {name, verb: req.verb, task: t, out, err, timeout, started: Date.now()};
}

function finish(job) {
  const t = job.task, code = t.terminationStatus, signaled = Number(t.terminationReason) === 2;   // NSTaskTerminationReasonUncaughtSignal
  const stdout = readText(job.out), stderr = readText(job.err);
  rm(job.out); rm(job.err);
  let res;
  if (signaled) {
    res = {ok: false, error: code === 14 ? 'timeout after ' + job.timeout + 's' : 'killed by signal ' + code, stdout, stderr};
  } else if (CHROME_VERBS.includes(job.verb)) {
    try {
      const r = JSON.parse(stdout);
      res = r.error ? {ok: false, error: r.error} : {ok: true, running: r.running, result: r.result};
    } catch (e) {
      res = {ok: false, error: (stderr || stdout || 'chrome.js failed').trim()};
    }
  } else if (code !== 0) {
    res = {ok: false, error: stderr.trim() || 'exit ' + code, code, stdout, stderr};
  } else {
    res = {ok: true, result: {code, stdout, stderr}};
  }
  writeText(RES + '/' + job.name, JSON.stringify(res));
}

function stuck(job) {
  try { job.task.terminate; } catch (e) {}
  const stdout = readText(job.out), stderr = readText(job.err);
  rm(job.out); rm(job.err);
  writeText(RES + '/' + job.name, JSON.stringify({ok: false, error: 'stuck: no exit ' + STUCK_GRACE_S + 's after the ' + job.timeout + 's timeout', stdout, stderr}));
}

function run() {
  for (const d of [ROOT, REQ, RES, TMP]) fm.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(d, true, $(), null);
  const jobs = [], born = Date.now();
  for (let idle = 0; idle < MAX_IDLE_LOOPS || jobs.length; idle++) {
    if (!jobs.length && Date.now() - born > MAX_UPTIME_S * 1000) break;
    for (const name of ls(REQ)) {
      if (name.startsWith('.') || !name.endsWith('.json')) continue;
      const p = REQ + '/' + name, text = readText(p);
      rm(p);
      idle = 0;
      try {
        const req = JSON.parse(text);
        if (req.verb === 'ping') writeText(RES + '/' + name, JSON.stringify({ok: true, result: 'pong'}));
        else jobs.push(start(name, req));
      } catch (e) {
        writeText(RES + '/' + name, JSON.stringify({ok: false, error: String(e.message || e)}));
      }
    }
    for (let i = jobs.length - 1; i >= 0; i--) {
      if (!jobs[i].task.isRunning) { finish(jobs[i]); jobs.splice(i, 1); }
      else if (Date.now() - jobs[i].started > (jobs[i].timeout + STUCK_GRACE_S) * 1000) { stuck(jobs[i]); jobs.splice(i, 1); }
    }
    if (idle % 300 === 0) for (const name of ls(RES)) if (ageS(RES + '/' + name) > RES_TTL_S) rm(RES + '/' + name);
    delay(jobs.length ? 0.05 : 0.2);
  }
}

MOBILE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1">
<meta name="theme-color" content="#FAF9F5">
<title>Claude Code</title>
<style>
:root{--bg:#FAF9F5;--bg2:#F0EEE6;--bg3:#E7E3D8;--text:#1F1D1B;--dim:#5C5952;
--faint:#8A867C;--line:#E6E2D7;--accent:#C96442;--red:#BF4A3E;--white:#fff}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
font-size:15px;overscroll-behavior:none}
/* Grid shell pinned to the visual viewport. Flex needed min-height:0 in three
   places before the composer stopped sliding off screen; grid rows do it
   declaratively and survive in-app browsers that mis-report 100dvh. */
body{position:fixed;inset:0;display:grid;grid-template-rows:auto 1fr auto;
height:auto;width:100%;overflow:hidden}
header{display:flex;align-items:center;gap:8px;padding:10px 12px;padding-top:calc(10px + env(safe-area-inset-top));
border-bottom:1px solid var(--line);background:var(--bg)}
header .brand{display:flex;align-items:center;gap:7px;font-weight:600;font-size:15px}
header .grow{flex:1}
header select{max-width:44vw;border:1px solid var(--line);background:var(--bg2);color:var(--text);
border-radius:8px;padding:6px 8px;font-size:12px;outline:none}
header .lang{flex:0 0 auto;width:auto;min-width:40px;padding:0 9px;font-size:12px;font-weight:600}
.icon{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border:1px solid var(--line);
background:var(--bg);border-radius:10px;color:var(--dim);font-size:16px;line-height:1}
main{min-height:0;overflow-y:auto;padding:14px 12px 8px;-webkit-overflow-scrolling:touch}
.wrap{max-width:720px;margin:0 auto}
.u{display:flex;justify-content:flex-end;margin:8px 0}
.u div{max-width:84%;background:var(--bg2);border-radius:16px 16px 4px 16px;padding:9px 12px;
white-space:pre-wrap;word-break:break-word;line-height:1.6}
.a{margin:10px 0;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.a code{background:var(--bg3);padding:1px 4px;border-radius:4px;font-size:13px}
details{margin:8px 0;border:1px solid var(--line);border-radius:10px;background:var(--bg2);overflow:hidden}
summary{padding:8px 10px;font-size:12.5px;color:var(--dim);list-style:none;display:flex;gap:6px;align-items:center}
summary::-webkit-details-marker{display:none}
details pre{margin:0;padding:2px 10px 10px;font-size:12px;color:var(--dim);white-space:pre-wrap;
word-break:break-word;max-height:42vh;overflow:auto;font-family:ui-monospace,Menlo,monospace}
.think{border-color:rgba(201,100,66,.28)}
.think summary{color:var(--accent)}
.err{color:var(--red);font-size:13px;margin:8px 0}
/* 审批卡片：手机上直接点允许/拒绝，不用回电脑 */
.appr{margin:10px 0;border:1px solid rgba(201,100,66,.5);border-radius:12px;
background:#fff;overflow:hidden;box-shadow:0 1px 3px rgba(31,29,27,.06)}
.appr.settled{border-color:var(--line);box-shadow:none;background:var(--bg2)}
.appr h4{margin:0;padding:9px 12px;font-size:13px;font-weight:600;color:var(--accent);
background:var(--bg2);display:flex;align-items:center;gap:8px}
.appr.settled h4{color:var(--dim)}
.appr h4 b{flex:1;font-weight:600}
.appr .rem{font-size:11px;font-weight:400;color:var(--faint);white-space:nowrap}
.appr pre{margin:0;padding:9px 12px;font-size:11.5px;line-height:1.55;color:var(--dim);
font-family:ui-monospace,Menlo,Consolas,monospace;max-height:34vh;overflow:auto;
white-space:pre-wrap;word-break:break-all;background:#fff}
.appr .acts{display:flex;gap:8px;padding:3px 12px 11px;flex-wrap:wrap}
.appr .acts button{border:0;border-radius:8px;padding:8px 15px;font:inherit;font-size:13px;
cursor:pointer;-webkit-appearance:none;appearance:none}
.appr .acts button:disabled{opacity:.5}
.appr .a-ok{background:var(--accent);color:#fff}
.appr .a-all{background:var(--bg3);color:var(--text)}
.appr .a-no{background:#F3E3DF;color:var(--red)}
.appr .done{padding:0 12px 11px;font-size:12px;color:var(--faint)}
.empty{color:var(--faint);text-align:center;padding:22vh 20px;font-size:13px;line-height:1.8}
footer{padding:8px 12px calc(10px + env(safe-area-inset-bottom));
border-top:1px solid var(--line);background:var(--bg)}
.box{max-width:720px;margin:0 auto;border:1px solid var(--line);border-radius:18px;
background:#F5F4EF;padding:9px 10px 8px}
textarea{width:100%;height:26px;min-height:26px;max-height:42vh;border:0;background:transparent;
color:var(--text);font:inherit;font-size:15px;line-height:1.5;resize:none;outline:none;padding:2px 3px;
overflow-y:hidden;field-sizing:content}
.row{display:flex;align-items:center;gap:6px;margin-top:6px}
.row .grow{flex:1}
.clip{display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;
color:var(--faint);font-size:17px}
#send{flex:0 0 32px;width:32px;min-width:32px;height:32px;padding:0;border-radius:50%;border:0;
background:#C96442;color:#fff;font-size:16px;line-height:1;display:flex;
align-items:center;justify-content:center;-webkit-appearance:none;appearance:none}
#send[disabled]{opacity:.45}
.pick{border:0;background:transparent;color:var(--dim);font-size:12px;padding:4px 6px;max-width:40vw;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip{font-size:11px;background:var(--bg3);color:var(--dim);border-radius:6px;padding:2px 6px;
max-width:30vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
aside{position:fixed;inset:0;background:rgba(31,29,27,.28);z-index:20;display:none}
aside.on{display:block}
.panel{position:absolute;left:0;top:0;bottom:0;width:84%;max-width:330px;background:var(--bg);
display:flex;flex-direction:column;box-shadow:2px 0 22px rgba(0,0,0,.16)}
.panel h3{margin:0;padding:14px 14px 8px;font-size:14px;display:flex;align-items:center;gap:8px}
.panel h3 span{flex:1}
.plist{flex:1;overflow-y:auto;padding:0 8px 14px}
.hrow{padding:9px 8px;border-radius:8px}
.hrow:active{background:var(--bg2)}
.hrow b{display:block;font-weight:500;font-size:13.5px;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}
.hrow i{display:block;font-style:normal;color:var(--faint);font-size:11px;margin-top:2px}
.newbtn{margin:0 14px 10px;padding:9px;border-radius:10px;border:1px solid var(--line);
background:var(--bg3);color:var(--text);font-size:13px}
</style>
</head>
<body>
<header>
  <button class="icon" id="openHist" aria-label="History">☰</button>
  <div class="brand"><svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true"><path fill="#C96442" d="m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"/></svg>
    Claude Code</div>
  <div class="grow"></div>
  <select id="model" aria-label="Choose a model"></select>
  <button class="icon lang" id="lang" aria-label="Language">中</button>
</header>
<main id="msgs"><div class="wrap" id="thread"><div class="empty" id="empty">Type below to start<br>Pick a model top-right · history top-left</div></div></main>
<footer>
  <div class="box">
    <textarea id="ta" rows="1" placeholder="Reply…" enterkeyhint="send"></textarea>
    <div class="row">
      <label class="clip" aria-label="Add attachment">＋<input id="file" type="file" accept="image/*" multiple hidden></label>
      <span id="att"></span>
      <span class="grow"></span>
      <button id="send" aria-label="Send">↑</button>
    </div>
  </div>
</footer>
<aside id="drawer">
  <div class="panel">
    <h3><span>History</span><button class="pick" id="closeHist">Close</button></h3>
    <button class="newbtn" id="newSess">＋ New chat</button>
    <div class="plist" id="plist"></div>
  </div>
</aside>
<script>
(function () {
  var qs = new URLSearchParams(location.search);
  var T = qs.get('t') || localStorage.getItem('ccp_t') || '';
  if (T) localStorage.setItem('ccp_t', T);
  var thread = document.getElementById('thread');
  var ta = document.getElementById('ta');
  var sendBtn = document.getElementById('send');
  var sel = document.getElementById('model');
  var list = document.getElementById('plist');
  var drawer = document.getElementById('drawer');
  var attBox = document.getElementById('att');
  var state = { sid: 'm-' + Date.now().toString(36), resume: null, cwd: '',
                job: null, busy: false, attachments: [] };

  /* ---- i18n：默认跟随浏览器语言，页头按钮切换并记住选择 ----
     A translation layer keyed by semantic name: every user-visible string on
     this page goes through t(), so adding a language means one dict here. */
  var STR = {
    en: {
      history: 'History', chooseModel: 'Choose a model', language: 'Language',
      emptyHint: 'Type below to start<br>Pick a model top-right · history top-left',
      placeholder: 'Reply…', addAttachment: 'Add attachment', send: 'Send',
      close: 'Close', newChat: '＋ New chat',
      thinking: 'Thinking', toolCall: 'Tool call', toolResult: 'Tool result · ',
      approvalNeeded: 'Approval needed · ', allow: 'Allow', alwaysAllow: 'Always allow',
      deny: 'Deny', allowed: 'Allowed',
      allowedSession: 'Allowed · this tool is always allowed for this session',
      allowedSessionShort: 'Allowed · always allowed in this session',
      denied: 'Denied', timedOutAuto: 'Timed out and auto-denied', timedOut: 'Timed out',
      approvalFailed: 'Approval failed: ', modelsFailed: 'Could not load models: ',
      loading: 'Loading…', noHistory: 'No past conversations yet',
      untitled: 'Untitled', turns: 'turns', loadFailed: 'Load failed: ',
      loadingSession: 'Loading conversation…', pickModel: 'Pick a model first',
      attachmentOnly: '(attachment)', sendFailed: 'Send failed: ',
      connLost: 'Connection lost: ', uploadFailed: 'Upload failed: ',
      error: 'Something went wrong', newChatHint: 'New chat · just start typing'
    },
    zh: {
      history: '历史会话', chooseModel: '选择模型', language: '语言',
      emptyHint: '在下面输入，开始对话<br>右侧可选模型，左上角是历史会话',
      placeholder: '回复…', addAttachment: '添加附件', send: '发送',
      close: '关闭', newChat: '＋ 新建会话',
      thinking: '思考过程', toolCall: '工具调用', toolResult: '工具返回 · ',
      approvalNeeded: '需要审批 · ', allow: '允许', alwaysAllow: '始终允许',
      deny: '拒绝', allowed: '已允许',
      allowedSession: '已允许 · 本会话对该工具始终放行',
      allowedSessionShort: '已允许 · 本会话始终放行',
      denied: '已拒绝', timedOutAuto: '已超时，自动拒绝', timedOut: '已超时',
      approvalFailed: '审批提交失败：', modelsFailed: '模型列表读取失败：',
      loading: '读取中…', noHistory: '还没有历史会话',
      untitled: '未命名会话', turns: '轮', loadFailed: '读取失败：',
      loadingSession: '读取历史会话…', pickModel: '请先选择模型',
      attachmentOnly: '（附件）', sendFailed: '发送失败：',
      connLost: '连接中断：', uploadFailed: '附件上传失败：',
      error: '出错', newChatHint: '新会话 · 直接输入即可'
    }
  }
  var LANG = (function () {
    var q = String(qs.get('lang') || '').toLowerCase()
    if (q === 'en' || q === 'zh') { try { localStorage.setItem('ccp_lang', q) } catch (e) {} return q }
    try {
      var saved = localStorage.getItem('ccp_lang')
      if (saved === 'en' || saved === 'zh') return saved
    } catch (e) {}
    return (navigator.language || '').toLowerCase().indexOf('zh') === 0 ? 'zh' : 'en'
  })()
  function t(k) {
    var pack = STR[LANG] || STR.en
    if (pack[k] != null) return pack[k]
    return STR.en[k] != null ? STR.en[k] : k
  }
  function applyStatic() {
    document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en'
    var empty = document.getElementById('empty')
    if (empty) empty.innerHTML = t('emptyHint')
    ta.placeholder = t('placeholder')
    sendBtn.setAttribute('aria-label', t('send'))
    sel.setAttribute('aria-label', t('chooseModel'))
    document.getElementById('openHist').setAttribute('aria-label', t('history'))
    document.getElementById('file').parentNode.setAttribute('aria-label', t('addAttachment'))
    document.getElementById('closeHist').textContent = t('close')
    var title = document.querySelector('.panel h3 span')
    if (title) title.textContent = t('history')
    document.getElementById('newSess').textContent = t('newChat')
    var lb = document.getElementById('lang')
    lb.textContent = LANG === 'zh' ? 'EN' : '中'
    lb.setAttribute('aria-label', t('language'))
    lb.onclick = function () {
      LANG = LANG === 'zh' ? 'en' : 'zh'
      try { localStorage.setItem('ccp_lang', LANG) } catch (e) {}
      location.reload()
    }
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return c === '&' ? '&amp;' : c === '<' ? '&lt;' : '&gt;'
    })
  }
  function api(path, opt) {
    opt = opt || {}
    return fetch('/api' + path, {
      method: opt.method || 'GET',
      headers: { 'content-type': 'application/json', 'x-ccp-mobile': T },
      body: opt.body ? JSON.stringify(opt.body) : undefined
    }).then(function (r) {
      if (!r.ok) return r.text().then(function (t) { throw new Error(r.status + ' ' + t.slice(0, 160)) })
      return r.json()
    })
  }
  function grow() {
    /* Measure from a fixed one-line box: `height:auto` inside a flex column
       expands to the whole viewport, which pushed the composer off screen. */
    var max = Math.round(window.innerHeight * 0.42)
    ta.style.height = '26px'
    var need = ta.scrollHeight || 26
    ta.style.height = Math.max(26, Math.min(need, max)) + 'px'
    ta.style.overflowY = need > max ? 'auto' : 'hidden'
  }
  function atBottom() { var m = document.getElementById('msgs'); return m.scrollHeight - m.scrollTop - m.clientHeight < 90 }
  function scroll(force) {
    var m = document.getElementById('msgs')
    if (force || atBottom()) m.scrollTop = m.scrollHeight
  }
  function clearEmpty() {
    var e = thread.querySelector('.empty')
    if (e) e.remove()
  }
  function addUser(text) {
    clearEmpty()
    var d = document.createElement('div')
    d.className = 'u'
    d.innerHTML = '<div>' + esc(text) + '</div>'
    thread.appendChild(d)
    scroll(true)
  }
  var live = null, liveThink = null, thinkBuf = '', sawDelta = false
  function addAssistant() {
    var d = document.createElement('div')
    d.className = 'a'
    thread.appendChild(d)
    live = d
    return d
  }
  function addThinking(text) {
    var s = String(text == null ? '' : text)
    if (!s) return
    if (!liveThink) {
      var t = document.createElement('details')
      t.className = 'think'
      t.open = true
      t.innerHTML = '<summary>' + t('thinking') + '</summary><pre></pre>'
      thread.appendChild(t)
      liveThink = t.querySelector('pre')
      thinkBuf = ''
      scroll(true)
    }
    liveThink.textContent += s
    thinkBuf += s
    scroll()
  }
  function addTool(hint, body) {
    var t = document.createElement('details')
    t.innerHTML = '<summary>' + esc(hint || t('toolCall')) + '</summary><pre>' + esc(body || '') + '</pre>'
    thread.appendChild(t)
    scroll()
  }
  function addError(text) {
    var d = document.createElement('div')
    d.className = 'err'
    d.textContent = text
    thread.appendChild(d)
    scroll(true)
  }

  /* ---- 审批：在手机上直接放行/拒绝，不再需要跑回电脑 ---- */
  var approvals = {}
  function addApproval(req) {
    if (!req || !req.id || approvals[req.id]) return
    var input = ''
    try { input = JSON.stringify(req.input || {}, null, 1) } catch (e) { input = '' }
    if (input.length > 1500) input = input.slice(0, 1500) + '\n…'
    var box = document.createElement('div')
    box.className = 'appr'
    box.innerHTML = '<h4><b>' + t('approvalNeeded') + esc(req.tool_name || t('toolCall')) +
      '</b><span class="rem"></span></h4>' +
      (input && input !== '{}' ? '<pre>' + esc(input) + '</pre>' : '') +
      '<div class="acts">' +
      '<button class="a-ok">' + t('allow') + '</button>' +
      '<button class="a-all">' + t('alwaysAllow') + '</button>' +
      '<button class="a-no">' + t('deny') + '</button></div>'
    thread.appendChild(box)
    approvals[req.id] = { el: box, deadline: Number(req.deadline || 0) }
    box.querySelector('.a-ok').addEventListener('click', function () { decide(req.id, 'allow') })
    box.querySelector('.a-all').addEventListener('click', function () { decide(req.id, 'always_allow') })
    box.querySelector('.a-no').addEventListener('click', function () { decide(req.id, 'deny') })
    tickApprovals()
    scroll(true)
  }
  function markApproval(id, text) {
    var rec = approvals[id]
    if (!rec || rec.settled) return
    rec.settled = true
    rec.el.classList.add('settled')
    var acts = rec.el.querySelector('.acts')
    if (acts) acts.parentNode.removeChild(acts)
    var rem = rec.el.querySelector('.rem')
    if (rem) rem.textContent = ''
    var d = document.createElement('div')
    d.className = 'done'
    d.textContent = text
    rec.el.appendChild(d)
  }
  async function decide(id, action) {
    var rec = approvals[id]
    if (!rec) return
    var btns = rec.el.querySelectorAll('.acts button')
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true
    try {
      await api('/approvals/decide', { method: 'POST', body: { id: id, action: action } })
      markApproval(id, action === 'deny' ? t('denied')
        : action === 'always_allow' ? t('allowedSession') : t('allowed'))
    } catch (e) {
      for (var j = 0; j < btns.length; j++) btns[j].disabled = false
      addError(t('approvalFailed') + e.message)
    }
  }
  function tickApprovals() {
    Object.keys(approvals).forEach(function (id) {
      var rec = approvals[id]
      var rem = rec && rec.el.querySelector('.rem')
      if (!rem || !rec.deadline) return
      var left = Math.round(rec.deadline - Date.now() / 1000)
      rem.textContent = left > 0
        ? (LANG === 'zh' ? left + ' 秒后自动拒绝' : 'auto-deny in ' + left + 's')
        : t('timedOut')
    })
  }
  setInterval(tickApprovals, 1000)
  async function loadApprovals() {
    try {
      var r = await api('/approvals')
      ;(r.pending || []).forEach(addApproval)
    } catch (e) { /* 审批接口不可用时静默，不打扰对话 */ }
  }
  function reset() { live = null; liveThink = null; thinkBuf = ''; sawDelta = false }
  function setBusy(v) {
    state.busy = v
    sendBtn.disabled = v
    sendBtn.textContent = v ? '■' : '↑'
  }

  var MODELS = []
  async function loadModels() {
    try {
      var m = await api('/models?probe=false')
      MODELS = m.models || []
      var groups = {}
      MODELS.forEach(function (x) { (groups[x.group] = groups[x.group] || []).push(x) })
      var html = ''
      Object.keys(groups).forEach(function (g) {
        html += '<optgroup label="' + esc(g) + '">'
        groups[g].forEach(function (x) {
          html += '<option value="' + esc(x.id) + '">' + esc(x.name || x.model) + '</option>'
        })
        html += '</optgroup>'
      })
      sel.innerHTML = html
      var rec = m.recommended
      var recId = typeof rec === 'string' ? rec
        : (rec && rec.provider ? (rec.provider + '/' + rec.model) : '')
      if (recId && MODELS.some(function (x) { return x.id === recId })) sel.value = recId
    } catch (e) { addError(t('modelsFailed') + e.message) }
  }

  async function loadHistory() {
    list.innerHTML = '<div class="hrow"><i>' + t('loading') + '</i></div>'
    try {
      var r = await api('/history?limit=60')
      if (!r.items || !r.items.length) { list.innerHTML = '<div class="hrow"><i>' + t('noHistory') + '</i></div>'; return }
      list.innerHTML = ''
      r.items.forEach(function (it) {
        var d = document.createElement('div')
        d.className = 'hrow'
        d.innerHTML = '<b>' + esc(it.title || t('untitled')) + '</b><i>' +
          esc((it.project_label || '') + ' · ' + (it.turns || 0) + ' ' + t('turns')) + '</i>'
        d.onclick = function () { openSession(it) }
        list.appendChild(d)
      })
    } catch (e) { list.innerHTML = '<div class="hrow"><i>' + t('loadFailed') + esc(e.message) + '</i></div>' }
  }

  async function openSession(it) {
    drawer.classList.remove('on')
    thread.innerHTML = '<div class="empty">' + t('loadingSession') + '</div>'
    try {
      var r = await api('/history/session?id=' + encodeURIComponent(it.id))
      thread.innerHTML = ''
      state.sid = 'm-' + it.id.slice(0, 8)
      state.resume = it.id
      state.cwd = (r.session && r.session.cwd) || it.cwd || ''
      ;(r.messages || []).forEach(function (m) {
        if (m.role === 'user') addUser(m.text)
        else if (m.role === 'assistant') { var d = addAssistant(); d.textContent = m.text; reset() }
        else if (m.role === 'thinking') addThinking(m.text)
        else if (m.role === 'tool') addTool(m.hint, m.text)
      })
      reset()
      scroll(true)
    } catch (e) { thread.innerHTML = '<div class="empty">' + t('loadFailed') + esc(e.message) + '</div>' }
  }

  function handle(ev) {
    if (!ev) return
    var k = ev.kind
    if (k === 'delta') {
      if (!live) addAssistant()
      sawDelta = true
      live.textContent += ev.text || ''
      scroll()
      return
    }
    /* 后端有两条路径会送达思考内容：模型网关发 reasoning_delta，
       Claude CLI 的 stream-json 发 thinking_delta，两种都要接。 */
    if (k === 'thinking_delta' || k === 'reasoning_delta') {
      addThinking(ev.text || '')
      return
    }
    if (k === 'reasoning_done') { liveThink = null; return }
    if (k === 'tool' || k === 'tool_call') {
      addTool(ev.hint || ev.name, ev.detail || ev.text || ev.args)
      return
    }
    if (k === 'blocks') {
      (ev.blocks || []).forEach(function (b) {
        if (!b) return
        if (b.type === 'text') {
          if (sawDelta) return   /* 增量已渲染过，整段再来一次会重复 */
          if (!live) addAssistant()
          live.textContent += b.text || ''
          scroll()
        } else if (b.type === 'thinking') {
          /* CLI 在增量之后会把整段思考再发一次，只补没见过的部分，避免重复 */
          var t = String(b.text || '')
          if (t && thinkBuf.indexOf(t.trim()) < 0) addThinking(t)
        } else if (b.type === 'tool') {
          addTool(b.name, b.input ? JSON.stringify(b.input).slice(0, 400) : '')
        } else if (b.type === 'tool_result') {
          addTool(t('toolResult') + (b.id || ''), String(b.text || '').slice(0, 1200))
        }
      })
      return
    }
    if (k === 'result') {
      if (ev.text && !live) { var d = addAssistant(); d.textContent = ev.text }
      reset()
      scroll(true)
      return
    }
    if (k === 'permission_request') { addApproval(ev); return }
    if (k === 'permission_resolved') {
      markApproval(ev.id, ev.action === 'deny' ? t('denied')
        : ev.action === 'timeout' ? t('timedOutAuto')
        : ev.action === 'always_allow' ? t('allowedSessionShort') : t('allowed'))
      return
    }
    if (k === 'error') addError(ev.error || ev.text || t('error'))
  }

  function poll(job) {
    var cursor = 0
    var stop = false
    state.job = job
    async function tick() {
      if (stop) return
      try {
        var r = await api('/poll?job_id=' + encodeURIComponent(job) + '&cursor=' + cursor)
        cursor = typeof r.cursor === 'number' ? r.cursor : cursor
        ;(r.events || []).forEach(handle)
        if (r.done) {
          if (r.error) addError(String(r.error))
          reset(); setBusy(false); scroll(true); return
        }
        setTimeout(tick, 400)
      } catch (e) { addError(t('connLost') + e.message); reset(); setBusy(false) }
    }
    tick()
  }

  async function send() {
    var text = ta.value.trim()
    if ((!text && !state.attachments.length) || state.busy) return
    var row = MODELS.filter(function (x) { return x.id === sel.value })[0] || MODELS[0]
    if (!row) { addError(t('pickModel')); return }
    addUser(text || t('attachmentOnly'))
    ta.value = ''; grow()
    setBusy(true)
    reset()
    var body = {
      text: text, provider: row.provider, model: row.model,
      session_key: state.sid, resume_id: state.resume || undefined,
      cwd: state.cwd || undefined,
      attachments: state.attachments.slice()
    }
    state.attachments = []; attBox.textContent = ''
    try {
      var r = await api('/chat', { method: 'POST', body: body })
      poll(r.job_id)
    } catch (e) { addError(t('sendFailed') + e.message); setBusy(false) }
  }

  async function upload(files) {
    for (var i = 0; i < files.length; i++) {
      var f = files[i]
      var data = await new Promise(function (res) {
        var fr = new FileReader(); fr.onload = function () { res(String(fr.result)) }; fr.readAsDataURL(f)
      })
      try {
        var r = await api('/upload', { method: 'POST', body: {
          name: f.name, mime: f.type || 'application/octet-stream', size: f.size,
          data: data, session_key: state.sid } })
        state.attachments.push({ path: r.path, name: r.name, mime: r.mime, kind: r.kind })
        var c = document.createElement('span')
        c.className = 'chip'; c.textContent = f.name
        attBox.appendChild(c)
      } catch (e) { addError(t('uploadFailed') + e.message) }
    }
  }

  sendBtn.onclick = function () { if (state.busy) { api('/cancel', { method: 'POST', body: { job_id: state.job } }); setBusy(false) } else send() }
  ta.addEventListener('input', grow)
  ta.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send() }
  })
  document.getElementById('file').onchange = function (e) { upload(e.target.files); e.target.value = '' }
  document.getElementById('openHist').onclick = function () { drawer.classList.add('on'); loadHistory() }
  document.getElementById('closeHist').onclick = function () { drawer.classList.remove('on') }
  drawer.onclick = function (e) { if (e.target === drawer) drawer.classList.remove('on') }
  document.getElementById('newSess').onclick = function () {
    drawer.classList.remove('on')
    state.sid = 'm-' + Date.now().toString(36); state.resume = null
    thread.innerHTML = '<div class="empty">' + t('newChatHint') + '</div>'
    reset()
  }
  applyStatic(); grow(); loadModels(); loadApprovals()
})()
</script>
</body>
</html>
"""

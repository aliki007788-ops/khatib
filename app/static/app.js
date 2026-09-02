let cid = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

const $ = id => document.getElementById(id);

async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: 'include', ...opts });
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    data = {};
  }
  if (!res.ok) {
    let msg = data.error || data.detail || ('خطا ' + res.status);
    if (typeof msg !== 'string') msg = JSON.stringify(msg);
    throw new Error(msg);
  }
  return data;
}

function goTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const tab = $('tab-' + name);
  if (tab) tab.classList.add('active');
  const nav = document.querySelector('.nav-item[data-tab="' + name + '"]');
  if (nav) nav.classList.add('active');
  if (name === 'profile') loadHistory();
  if (name === 'speech') loadTip();
  if (name === 'chat' && $('chatbox') && !$('chatbox').children.length) {
    $('chatbox').innerHTML = '<div class="msg">أهلاً! شلونك؟ من مربی خطیب هستم. بگو می‌خوای تمرین سخنرانی کنیم یا مکالمه عراقی؟</div>';
  }
}

async function register() {
  const name = (($('name') && $('name').value) || '').trim();
  const email = (($('email') && $('email').value) || '').trim();
  const password = (($('pass') && $('pass').value) || '');
  if (!email || !password) {
    if ($('authmsg')) $('authmsg').textContent = 'ایمیل و رمز را وارد کنید';
    alert('ایمیل و رمز را وارد کنید');
    return;
  }
  if (password.length < 8) {
    if ($('authmsg')) $('authmsg').textContent = 'رمز باید حداقل ۸ کاراکتر باشد';
    alert('رمز باید حداقل ۸ کاراکتر باشد');
    return;
  }
  if ($('authmsg')) $('authmsg').textContent = 'در حال ثبت‌نام...';
  const f = new FormData();
  f.append('name', name || 'کاربر');
  f.append('email', email);
  f.append('password', password);
  try {
    const reg = await api('/api/register', { method: 'POST', body: f });
    if ($('authmsg')) $('authmsg').textContent = 'ثبت‌نام موفق';
    if (reg && reg.user) {
      showApp(reg);
      return;
    }
    await login();
  } catch (e) {
    if ($('authmsg')) $('authmsg').textContent = e.message || 'خطا در ثبت‌نام';
    alert(e.message || 'خطا در ثبت‌نام');
  }
}

async function login() {
  const email = (($('email') && $('email').value) || '').trim();
  const password = (($('pass') && $('pass').value) || '');
  if (!email || !password) {
    if ($('authmsg')) $('authmsg').textContent = 'ایمیل و رمز را وارد کنید';
    alert('ایمیل و رمز را وارد کنید');
    return;
  }
  if ($('authmsg')) $('authmsg').textContent = 'در حال ورود...';
  const f = new FormData();
  f.append('email', email);
  f.append('password', password);
  try {
    const u = await api('/api/login', { method: 'POST', body: f });
    showApp(u);
  } catch (e) {
    if ($('authmsg')) $('authmsg').textContent = e.message || 'خطا در ورود';
    alert(e.message || 'خطا در ورود');
  }
}

async function check() {
  try {
    const u = await api('/api/me');
    if (u && u.logged && u.user) {
      showApp(u);
    } else {
      $('auth-screen').hidden = false;
      $('main-app').hidden = true;
    }
  } catch (e) {
    $('auth-screen').hidden = false;
    $('main-app').hidden = true;
  }
}

function showApp(payload) {
  const u = payload && payload.user ? payload.user : payload;
  if (!u) {
    alert('ورود ناموفق');
    return;
  }
  $('auth-screen').hidden = true;
  $('main-app').hidden = false;
  if ($('welcome-name')) $('welcome-name').textContent = 'سلام ' + (u.name || '') + ' 👋';
  if ($('prof-name')) $('prof-name').textContent = u.name || 'کاربر';
  if ($('prof-email')) $('prof-email').textContent = u.email || '';
  const plan = u.plan || 'free';
  if ($('user-level')) {
    $('user-level').textContent = plan === 'pro' ? 'حرفه‌ای' : plan === 'base' ? 'پایه' : 'مبتدی';
  }
  if ($('st-plan')) {
    $('st-plan').textContent = u.plan_name || (plan === 'pro' ? 'حرفه‌ای' : plan === 'base' ? 'پایه' : 'رایگان');
  }
  goTab('home');
  loadStats();
  loadSubscription();
}

async function loadStats() {
  try {
    const list = await api('/api/speeches');
    if ($('st-speech') && Array.isArray(list)) {
      $('st-speech').textContent = list.length;
      if (list.length && $('st-score')) {
        const best = Math.max.apply(null, list.map(function (x) { return x.score || 0; }));
        $('st-score').textContent = best;
      }
    }
  } catch (e) {}
}

async function loadSubscription() {
  try {
    const s = await api('/api/subscription');
    if (s.error) return;
    if ($('st-plan')) $('st-plan').textContent = s.plan_name || s.plan;
    if ($('st-speech')) {
      $('st-speech').textContent = (s.monthly_speech_count || 0) + '/' + (s.speech_limit || '∞');
    }
  } catch (e) {}
}

async function logout() {
  try { await api('/api/logout', { method: 'POST' }); } catch (e) {}
  location.reload();
}

async function loadTip() {
  try {
    const topic = ($('topic') && $('topic').value) || 'سخنرانی عمومی';
    const t = await api('/api/speech/coach-tip?topic=' + encodeURIComponent(topic));
    if ($('coach-tip')) $('coach-tip').textContent = '💡 ' + (t.tip || '');
  } catch (e) {
    if ($('coach-tip')) $('coach-tip').textContent = '💡 نفس عمیق بکش و با اعتماد شروع کن.';
  }
}

async function analyzeText() {
  const topic = ($('topic') && $('topic').value) || 'تمرین آزاد';
  const text = ($('speechtext') && $('speechtext').value) || '';
  if (!text.trim()) {
    alert('متن سخنرانی را بنویس یا صدا ضبط کن.');
    return;
  }
  if ($('rec-status')) $('rec-status').textContent = 'در حال تحلیل...';
  try {
    const f = new FormData();
    f.append('topic', topic);
    f.append('text', text);
    const a = await api('/api/speech', { method: 'POST', body: f });
    showResult(a);
  } catch (e) {
    if ($('rec-status')) $('rec-status').textContent = e.message;
    alert(e.message);
  }
}

function showResult(a) {
  if (!$('result-box')) return;
  $('result-box').hidden = false;
  if ($('score-display')) $('score-display').textContent = (a.score || 0) + '/100';
  if ($('fb-strengths')) {
    $('fb-strengths').innerHTML = (a.strengths || []).map(function (x) { return '<li>' + x + '</li>'; }).join('') || '<li>—</li>';
  }
  if ($('fb-weaknesses')) {
    $('fb-weaknesses').innerHTML = (a.weaknesses || []).map(function (x) { return '<li>' + x + '</li>'; }).join('') || '<li>—</li>';
  }
  if ($('fb-improvements')) {
    $('fb-improvements').innerHTML = (a.improvements || []).map(function (x) { return '<li>' + x + '</li>'; }).join('') || '<li>—</li>';
  }
  var extra = '';
  if (a.dsp) {
    var d = a.dsp;
    extra += '<div class="structure">🎚️ انرژی: ' + (d.energy_level || '—') +
      ' | pitch: ' + (d.pitch_hz || '—') + 'Hz | سکوت: ' +
      (d.silence_ratio != null ? Math.round(d.silence_ratio * 100) + '%' : '—') + '</div>';
  }
  if (a.prosody) {
    var p = a.prosody;
    extra += '<div class="structure" style="margin-top:10px">📊 کلمات: ' + (p.words || 0) +
      ' | جملات: ' + (p.sentences || 0) + ' | پرکننده: ' + (p.filler_count || 0);
    if (p.wpm) extra += ' | سرعت≈' + p.wpm + ' ک/د';
    if (p.duration_sec) extra += ' | مدت≈' + p.duration_sec + 'ث';
    extra += '</div>';
  }
  if (a.ai_mode) {
    extra += '<div class="structure">حالت تحلیل: ' + (a.ai_mode === 'remote' ? 'هوش مصنوعی' : 'محلی تقویت‌شده') + '</div>';
  }
  if ($('fb-structure')) $('fb-structure').innerHTML = (a.structure_notes || '') + extra;
  if ($('fb-next')) $('fb-next').textContent = '🎯 ' + (a.next_practice || 'دوباره تمرین کن.');
  if (a.transcript && $('speechtext')) $('speechtext').value = a.transcript;
  if ($('rec-status')) $('rec-status').textContent = '';
  loadStats();
  loadSubscription();
}

function resetSpeech() {
  if ($('result-box')) $('result-box').hidden = true;
  if ($('speechtext')) $('speechtext').value = '';
  if ($('rec-status')) $('rec-status').textContent = '';
  loadTip();
}

async function toggleRecord() {
  if (isRecording) {
    stopRecord();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = function (e) { audioChunks.push(e.data); };
    mediaRecorder.onstop = async function () {
      stream.getTracks().forEach(function (t) { t.stop(); });
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      await uploadAudio(blob);
    };
    mediaRecorder.start();
    isRecording = true;
    if ($('rec-btn')) {
      $('rec-btn').classList.add('recording');
      $('rec-btn').textContent = '⏹️ توقف ضبط';
    }
    if ($('rec-status')) $('rec-status').textContent = 'در حال ضبط... صحبت کنید';
  } catch (e) {
    if ($('rec-status')) $('rec-status').textContent = 'دسترسی به میکروفون ممکن نیست.';
    alert('دسترسی به میکروفون ممکن نیست.');
  }
}

function stopRecord() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    if ($('rec-btn')) {
      $('rec-btn').classList.remove('recording');
      $('rec-btn').textContent = '🎙️ شروع ضبط';
    }
    if ($('rec-status')) $('rec-status').textContent = 'در حال ارسال و تحلیل صدا...';
  }
}

async function uploadAudio(blob) {
  const topic = ($('topic') && $('topic').value) || 'تمرین صوتی';
  const f = new FormData();
  f.append('topic', topic);
  f.append('audio', blob, 'speech.webm');
  try {
    const a = await api('/api/speech/audio', { method: 'POST', body: f });
    if (a.job_id) {
      if ($('rec-status')) $('rec-status').textContent = 'در صف پردازش...';
      await pollJob(a.job_id);
      return;
    }
    showResult(a);
  } catch (e) {
    if ($('rec-status')) $('rec-status').textContent = e.message;
    alert(e.message);
  }
}

async function pollJob(jobId) {
  for (var i = 0; i < 60; i++) {
    await new Promise(function (r) { setTimeout(r, 1000); });
    try {
      const j = await api('/api/speech/job/' + jobId);
      if (j.status === 'done' && j.result) {
        showResult(j.result);
        return;
      }
      if (j.status === 'error') throw new Error(j.error || 'خطا در پردازش');
    } catch (e) {
      if ($('rec-status')) $('rec-status').textContent = e.message;
    }
  }
  if ($('rec-status')) $('rec-status').textContent = 'زمان پردازش تمام شد';
}

async function sendChat() {
  const m = (($('msg') && $('msg').value) || '').trim();
  if (!m) return;
  $('chatbox').innerHTML += '<div class="msg me">' + m + '</div>';
  $('msg').value = '';
  $('chatbox').scrollTop = $('chatbox').scrollHeight;
  try {
    const f = new FormData();
    f.append('message', m);
    if (cid) f.append('conversation_id', cid);
    const a = await api('/api/chat', { method: 'POST', body: f });
    cid = a.conversation_id;
    $('chatbox').innerHTML += '<div class="msg">' + (a.answer || '') + '</div>';
    $('chatbox').scrollTop = $('chatbox').scrollHeight;
  } catch (e) {
    $('chatbox').innerHTML += '<div class="msg">خطا: ' + e.message + '</div>';
  }
}

async function doTranslate() {
  const text = (($('src-text') && $('src-text').value) || '').trim();
  if (!text) return;
  try {
    const f = new FormData();
    f.append('text', text);
    const a = await api('/api/translate', { method: 'POST', body: f });
    $('trans-result').hidden = false;
    $('trans-main').textContent = a.translated || '—';
    $('trans-sub').textContent = a.sub || (a.detected === 'fa' ? 'ترجمه به عراقی' : 'ترجمه به فارسی');
  } catch (e) {
    alert(e.message);
  }
}

function useTopic(t) {
  if ($('topic')) $('topic').value = t;
  goTab('speech');
  loadTip();
}

function speakAr(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'ar-SA';
  u.rate = 0.9;
  speechSynthesis.speak(u);
}

async function buy(plan) {
  try {
    const f = new FormData();
    f.append('plan', plan);
    const a = await api('/api/subscribe', { method: 'POST', body: f });
    if ($('paymsg')) $('paymsg').textContent = a.message || 'درخواست ثبت شد';
    if (a.redirect) window.location.href = a.redirect;
  } catch (e) {
    if ($('paymsg')) $('paymsg').textContent = e.message;
    alert(e.message);
  }
}

async function loadHistory() {
  try {
    const a = await api('/api/speeches');
    if (!$('historybox')) return;
    $('historybox').innerHTML = (a && a.length)
      ? a.map(function (x) {
          return '<div class="item"><b>' + (x.topic || '') + '</b> — ' + (x.score || 0) + '/100<br><small>' +
            (x.text ? x.text.slice(0, 120) + '...' : '') + '</small></div>';
        }).join('')
      : '<p class="msg-hint">هنوز تمرینی ثبت نشده.</p>';
  } catch (e) {
    if ($('historybox')) $('historybox').innerHTML = '';
  }
}

check();
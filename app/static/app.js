/* ═══════════════════════════════════════════════════════════════
   ProfMatch AI — Frontend JavaScript
   Handles: multi-step form, tag inputs, search polling,
            email studio modal, dashboard actions, toasts
   ═══════════════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────────────
let currentStep = 1;
let currentProfId = null;
let searchPollInterval = null;

// ── DOMContentLoaded ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTagInputs();
  initProfileForm();
  initSearch();
  initDashboard();
  populateSavedTags();
  initScrollReveal();
  initDropZone();
});

// ══════════════════════════════════════════════════════════════
//  MULTI-STEP FORM
// ══════════════════════════════════════════════════════════════
function goToStep(n) {
  if (n === 2) {
    if (!validateStep1()) return;
  }

  // Hide all steps
  document.querySelectorAll('.form-step').forEach(s => s.classList.remove('active'));
  // Show target
  const target = document.getElementById(`step-${n}`);
  if (target) {
    target.classList.add('active');
    currentStep = n;
  }

  // Update indicator
  document.querySelectorAll('.step').forEach((el, idx) => {
    el.classList.remove('active', 'done');
    const stepNum = idx / 2 + 1; // account for connectors
  });

  const indicators = document.querySelectorAll('.step');
  indicators.forEach((el, i) => {
    const s = i + 1;
    el.classList.remove('active','done');
    if (s < n)      el.classList.add('done');
    else if (s === n) el.classList.add('active');
  });

  // Build profile summary on step 3
  if (n === 3) buildProfileSummary();
}

function validateStep1() {
  const name = val('name');
  const email = val('email');
  const university = val('university');

  if (!name) { showToast('error', '⚠ Please enter your full name.'); return false; }
  if (!email || !email.includes('@')) { showToast('error', '⚠ Please enter a valid email.'); return false; }
  if (!university) { showToast('error', '⚠ Please enter your university name.'); return false; }
  return true;
}

function buildProfileSummary() {
  const container = document.getElementById('profile-summary');
  if (!container) return;

  const interests = document.getElementById('research_interests')?.value || '';
  const items = [
    { key: 'Name',       val: val('name') },
    { key: 'University', val: val('university') },
    { key: 'Degree',     val: val('degree') + ' — ' + val('year') },
    { key: 'CGPA',       val: val('cgpa') || '—' },
    { key: 'Interests',  val: interests.split(',').slice(0,4).join(', ') || '—' },
    { key: 'GitHub',     val: val('github_url') || '—' },
    { key: 'Target',     val: val('target_institution') || 'Any institution' },
    { key: 'Duration',   val: val('internship_duration') },
  ];

  container.innerHTML = items.map(item => `
    <div class="summary-item">
      <span class="summary-key">${item.key}</span>
      <span class="summary-val">${escHtml(item.val)}</span>
    </div>
  `).join('');
}

// ══════════════════════════════════════════════════════════════
//  TAG INPUTS
// ══════════════════════════════════════════════════════════════
function initTagInputs() {
  setupTagInput('research-interests-input', 'research-tags', 'research_interests');
  setupTagInput('skills-input', 'skills-tags', 'skills');
}

function setupTagInput(inputId, listId, hiddenId) {
  const input  = document.getElementById(inputId);
  const list   = document.getElementById(listId);
  const hidden = document.getElementById(hiddenId);
  if (!input || !list || !hidden) return;

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const text = input.value.trim().replace(/,+$/, '');
      if (text) { addTag(text, list, hidden); input.value = ''; }
    }
    if (e.key === 'Backspace' && input.value === '') {
      const tags = list.querySelectorAll('.tag-item');
      if (tags.length) tags[tags.length - 1].remove();
      syncHidden(list, hidden);
    }
  });

  // Click wrapper to focus input
  const wrapper = document.getElementById(inputId.replace('-input', '-wrapper'));
  if (wrapper) wrapper.addEventListener('click', () => input.focus());
}

function addTag(text, list, hidden) {
  const existing = Array.from(list.querySelectorAll('.tag-item'))
    .map(t => t.dataset.val.toLowerCase());
  if (existing.includes(text.toLowerCase())) return;

  const tag = document.createElement('span');
  tag.className = 'tag-item';
  tag.dataset.val = text;
  tag.innerHTML = `${escHtml(text)}<span class="tag-remove" aria-label="Remove tag" onclick="removeTag(this)">×</span>`;
  list.appendChild(tag);
  syncHidden(list, hidden);
}

function removeTag(btn) {
  const tag    = btn.parentElement;
  const list   = tag.parentElement;
  const listId = list.id;
  const hiddenId = listId === 'research-tags' ? 'research_interests' : 'skills';
  const hidden = document.getElementById(hiddenId);
  tag.remove();
  syncHidden(list, hidden);
}

function syncHidden(list, hidden) {
  if (!hidden) return;
  const values = Array.from(list.querySelectorAll('.tag-item')).map(t => t.dataset.val);
  hidden.value = values.join(',');
}

function populateSavedTags() {
  // Populate tags from saved profile or demo on page load
  const riHidden = document.getElementById('research_interests');
  const skHidden = document.getElementById('skills');
  const riList   = document.getElementById('research-tags');
  const skList   = document.getElementById('skills-tags');

  if (riHidden && riList && riHidden.value) {
    riHidden.value.split(',').filter(Boolean).forEach(t =>
      addTag(t.trim(), riList, riHidden)
    );
  }
  if (skHidden && skList && skHidden.value) {
    skHidden.value.split(',').filter(Boolean).forEach(t =>
      addTag(t.trim(), skList, skHidden)
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  DEMO PROFILE LOADER
// ══════════════════════════════════════════════════════════════
function loadDemoProfile() {
  if (typeof DEMO_PROFILE === 'undefined') return;
  const p = DEMO_PROFILE;

  setVal('name',       p.name);
  setVal('email',      p.email);
  setVal('university', p.university);
  setVal('year',       p.year);
  setVal('cgpa',       p.cgpa);
  setVal('bio',        p.bio);
  setVal('achievements', p.achievements);
  setVal('github_url',   p.github_url);
  setVal('linkedin_url', p.linkedin_url);
  setVal('projects',   Array.isArray(p.projects) ? p.projects.join('\n') : p.projects);
  setVal('target_institution', p.target_institution || '');

  // Tags
  const riList   = document.getElementById('research-tags');
  const riHidden = document.getElementById('research_interests');
  const skList   = document.getElementById('skills-tags');
  const skHidden = document.getElementById('skills');

  if (riList) { riList.innerHTML = ''; riHidden.value = ''; }
  if (skList) { skList.innerHTML = ''; skHidden.value = ''; }

  const interests = Array.isArray(p.research_interests) ? p.research_interests : String(p.research_interests).split(',');
  interests.filter(Boolean).forEach(t => addTag(t.trim(), riList, riHidden));

  const skills = Array.isArray(p.skills) ? p.skills : String(p.skills).split(',');
  skills.filter(Boolean).forEach(t => addTag(t.trim(), skList, skHidden));

  showToast('success', '✨ Demo profile loaded successfully!');
}

// ══════════════════════════════════════════════════════════════
//  SEARCH FORM SUBMISSION & PROGRESS POLLING
// ══════════════════════════════════════════════════════════════
function initProfileForm() {
  const form = document.getElementById('profile-form');
  if (!form) return;

  form.addEventListener('submit', async e => {
    e.preventDefault();

    const riField = document.getElementById('research_interests')?.value;
    if (!riField) {
      showToast('error', '⚠ Please add at least one research interest.');
      if (currentStep === 3) goToStep(2);
      return;
    }

    await runSearch(collectFormData());
  });
}

function collectFormData() {
  const data = {};
  const form = document.getElementById('profile-form');
  if (!form) return data;

  new FormData(form).forEach((v, k) => { data[k] = v; });

  // Override with hidden tag values
  data.research_interests = document.getElementById('research_interests')?.value || '';
  data.skills = document.getElementById('skills')?.value || '';

  return data;
}

async function runSearch(formData) {
  const btn = document.getElementById('search-btn');
  const progressContainer = document.getElementById('search-progress-container');

  if (btn) { btn.classList.add('loading'); btn.disabled = true; }
  if (progressContainer) progressContainer.classList.remove('hidden');

  updateProgress(5, 'Sending your profile…');

  try {
    const resp = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });

    if (!resp.ok) throw new Error(await resp.text());
    pollSearchStatus();

  } catch (err) {
    showToast('error', `Search failed: ${err.message}`);
    if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
  }
}

function pollSearchStatus() {
  if (searchPollInterval) clearInterval(searchPollInterval);

  const sources = ['src-ss', 'src-ddg', 'src-gs'];
  let srcIdx = 0;

  searchPollInterval = setInterval(async () => {
    try {
      const resp = await fetch('/api/search/status');
      const data = await resp.json();

      updateProgress(data.progress || 0, data.message || '');

      // Animate source chips
      if (data.progress > 20 && srcIdx < sources.length) {
        document.getElementById(sources[srcIdx])?.classList.add('active');
        srcIdx++;
      }

      if (data.status === 'done') {
        clearInterval(searchPollInterval);
        showToast('success', `🎉 Found ${data.results.length} professors! Redirecting…`);
        setTimeout(() => { window.location.href = '/results'; }, 1200);
      } else if (data.status === 'error') {
        clearInterval(searchPollInterval);
        showToast('error', `Search error: ${data.error}`);
        const btn = document.getElementById('search-btn');
        if (btn) { btn.classList.remove('loading'); btn.disabled = false; }
      }
    } catch (e) {
      console.error('Poll error', e);
    }
  }, 1000);
}

function updateProgress(pct, msg) {
  const bar  = document.getElementById('progress-bar');
  const pctEl = document.getElementById('progress-pct');
  const msgEl = document.getElementById('progress-message');
  if (bar)   bar.style.width  = `${pct}%`;
  if (pctEl) pctEl.textContent = `${pct}%`;
  if (msgEl) msgEl.textContent = msg;
}

// ══════════════════════════════════════════════════════════════
//  RESULTS PAGE — FILTERING & EXPORT
// ══════════════════════════════════════════════════════════════
function filterProfessors() {
  const grade  = document.getElementById('filter-grade')?.value.toLowerCase() || '';
  const status = document.getElementById('filter-status')?.value.toLowerCase() || '';
  const search = document.getElementById('filter-search')?.value.toLowerCase() || '';

  const cards = document.querySelectorAll('.prof-card');
  let visible = 0;

  cards.forEach(card => {
    const cardGrade  = card.dataset.grade?.toLowerCase() || '';
    const cardStatus = card.dataset.status?.toLowerCase() || '';
    const cardName   = card.dataset.name || '';
    const cardUni    = card.dataset.uni  || '';

    const matchGrade  = !grade  || cardGrade  === grade;
    const matchStatus = !status || cardStatus === status;
    const matchSearch = !search || cardName.includes(search) || cardUni.includes(search);

    const show = matchGrade && matchStatus && matchSearch;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  });

  const countEl = document.getElementById('results-count');
  if (countEl) countEl.textContent = `${visible} result${visible !== 1 ? 's' : ''}`;
}

function exportResults() {
  if (typeof PROFESSORS === 'undefined' || !PROFESSORS.length) return;

  const headers = ['Name','University','Department','Email','Match Score','Match Grade','Research Areas','Scholar URL'];
  const rows = PROFESSORS.map(p => [
    p.name, p.university, p.department, p.email,
    p.match_score, p.match_grade,
    (p.research_areas || []).join('; '),
    p.scholar_url,
  ]);

  const csv = [headers, ...rows]
    .map(row => row.map(c => `"${String(c||'').replace(/"/g,'""')}"`).join(','))
    .join('\n');

  const blob = new Blob([csv], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `profmatch_results_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('success', '📥 CSV exported!');
}

// ══════════════════════════════════════════════════════════════
//  EMAIL STUDIO MODAL
// ══════════════════════════════════════════════════════════════
async function openEmailStudio(profId, profName) {
  currentProfId = profId;

  const modal    = document.getElementById('email-modal');
  const subtitle = document.getElementById('modal-prof-name');
  const genArea  = document.getElementById('email-generating');
  const editor   = document.getElementById('email-editor');

  if (!modal) return;

  subtitle.textContent = `Professor ${profName}`;
  genArea.classList.remove('hidden');
  editor.classList.add('hidden');
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  try {
    const resp = await fetch('/api/generate-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ professor_id: profId }),
    });

    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();

    document.getElementById('email-subject').value = data.subject || '';
    document.getElementById('email-body').value    = data.body    || '';

    const badge = document.getElementById('email-method-badge');
    if (data.method === 'ai') {
      badge.textContent = '🤖 AI Generated';
      badge.style.background = 'hsla(145,63%,49%,0.12)';
      badge.style.color = 'var(--success)';
    } else {
      badge.textContent = '📝 Template Generated';
      badge.style.background = 'hsla(252,100%,68%,0.1)';
      badge.style.color = 'var(--accent)';
    }

    genArea.classList.add('hidden');
    editor.classList.remove('hidden');

  } catch (err) {
    closeEmailStudio();
    showToast('error', `Failed to generate email: ${err.message}`);
  }
}

function closeEmailStudio() {
  const modal = document.getElementById('email-modal');
  if (modal) modal.classList.add('hidden');
  document.body.style.overflow = '';
  currentProfId = null;
}

async function regenerateEmail() {
  if (!currentProfId) return;
  const profName = document.getElementById('modal-prof-name')?.textContent?.replace('Professor ', '') || '';
  await openEmailStudio(currentProfId, profName);
}

function copyEmail() {
  const subject = document.getElementById('email-subject')?.value || '';
  const body    = document.getElementById('email-body')?.value    || '';
  const text = `Subject: ${subject}\n\n${body}`;

  navigator.clipboard.writeText(text).then(() => {
    showToast('success', '📋 Email copied to clipboard!');
  }).catch(() => {
    showToast('error', 'Copy failed — try manually selecting the text.');
  });
}

async function sendEmail() {
  if (!currentProfId) return;

  const subject = document.getElementById('email-subject')?.value?.trim();
  const body    = document.getElementById('email-body')?.value?.trim();

  if (!subject || !body) {
    showToast('error', '⚠ Subject and body cannot be empty.');
    return;
  }

  const btn = document.getElementById('send-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Sending…'; }

  try {
    const resp = await fetch('/api/send-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        professor_id: currentProfId,
        subject, body,
        schedule_followup: true,
      }),
    });

    const data = await resp.json();

    if (data.success) {
      showToast('success', '🚀 Email sent! Follow-up scheduled automatically.');
      if (data.followup_scheduled) showToast('info', `⏰ Follow-up will be sent in ${data.followup_days || 3} days.`);
      markCardContacted(currentProfId);
      closeEmailStudio();
      launchConfetti();
    } else {
      showToast('error', data.message || 'Send failed.');
    }
  } catch (err) {
    showToast('error', `Error: ${err.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🚀 Send Email'; }
  }
}

async function previewSend() {
  if (!currentProfId) return;

  const subject = document.getElementById('email-subject')?.value?.trim();
  const body    = document.getElementById('email-body')?.value?.trim();

  const resp = await fetch('/api/preview-send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ professor_id: currentProfId, subject, body }),
  });
  const data = await resp.json();

  if (data.success) {
    showToast('success', '👁 Marked as sent in tracking dashboard.');
    markCardContacted(currentProfId);
    closeEmailStudio();
  } else {
    showToast('error', data.error || 'Failed to mark sent.');
  }
}

function markCardContacted(profId) {
  const card = document.getElementById(`prof-card-${profId}`);
  if (card) {
    card.classList.add('contacted');
    card.dataset.status = 'contacted';
    if (!card.querySelector('.contacted-badge')) {
      const badge = document.createElement('div');
      badge.className = 'contacted-badge';
      badge.textContent = '✉ Contacted';
      card.appendChild(badge);
    }
  }
}

// Close modal on overlay click
document.addEventListener('click', e => {
  const modal = document.getElementById('email-modal');
  if (modal && e.target === modal) closeEmailStudio();

  const viewModal = document.getElementById('email-view-modal');
  if (viewModal && e.target === viewModal) closeViewModal();
});

// Keyboard: Escape to close
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeEmailStudio(); closeViewModal(); }
});

// ══════════════════════════════════════════════════════════════
//  DASHBOARD ACTIONS
// ══════════════════════════════════════════════════════════════
function initDashboard() {
  // Auto-refresh stats every 30s
  if (document.getElementById('stats-grid')) {
    setInterval(refreshStats, 30000);
  }
}

async function refreshDashboard() {
  window.location.reload();
}

async function refreshStats() {
  try {
    const resp = await fetch('/api/stats');
    const stats = await resp.json();

    // Update individual stat elements by their ID (set directly in index.html)
    const directIds = {
      'stat-matched':    stats.total_professors,
      'stat-sent':       stats.emails_sent,
      'stat-replies':    stats.reply_rate,
      'stat-interviews': stats.interviews,
    };

    Object.entries(directIds).forEach(([id, newVal]) => {
      const el = document.getElementById(id);
      if (el && el.textContent !== String(newVal ?? '')) {
        el.textContent = newVal ?? 0;
        el.classList.add('flash');
        setTimeout(() => el.classList.remove('flash'), 600);
      }
    });
  } catch (e) { /* silent */ }
}

async function markReplied(emailId) {
  try {
    const resp = await fetch('/api/mark-replied', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_id: emailId }),
    });
    const data = await resp.json();
    if (data.success) {
      const pill = document.querySelector(`#log-row-${emailId} .status-pill`);
      if (pill) {
        pill.className = 'status-pill status-replied';
        pill.textContent = '💬 Replied';
      }
      // Remove mark-replied button
      const btn = document.querySelector(`#log-row-${emailId} .btn-icon-green`);
      if (btn) btn.remove();
      showToast('success', '✅ Email marked as replied!');
      setTimeout(refreshStats, 500);
    }
  } catch (e) {
    showToast('error', 'Failed to update status.');
  }
}

function viewEmailBody(emailId) {
  const log = (typeof EMAIL_LOGS !== 'undefined' ? EMAIL_LOGS : []).find(l => l.id === emailId);
  if (!log) return;

  document.getElementById('email-view-subject').textContent = log.subject || '(No subject)';
  document.getElementById('email-view-body').textContent    = log.body    || '(No body)';
  document.getElementById('email-view-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeViewModal() {
  const m = document.getElementById('email-view-modal');
  if (m) m.classList.add('hidden');
  document.body.style.overflow = '';
}

function filterLog() {
  const q = document.getElementById('log-search')?.value.toLowerCase() || '';
  document.querySelectorAll('.log-row').forEach(row => {
    const name  = row.dataset.name  || '';
    const email = row.dataset.email || '';
    row.style.display = (!q || name.includes(q) || email.includes(q)) ? '' : 'none';
  });
}

// ══════════════════════════════════════════════════════════════
//  TOAST NOTIFICATIONS
// ══════════════════════════════════════════════════════════════
function showToast(type, message, duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.style.pointerEvents = 'all';
  toast.innerHTML = `<span style="flex-shrink:0;">${icons[type] || ''}</span><span>${escHtml(message)}</span>`;

  // Click to dismiss
  toast.addEventListener('click', () => {
    toast.classList.add('hiding');
    setTimeout(() => toast.remove(), 280);
  });

  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentNode) {
      toast.classList.add('hiding');
      setTimeout(() => toast.remove(), 280);
    }
  }, duration);
}

// ══════════════════════════════════════════════════════════════
//  CONFETTI (lightweight canvas confetti for send success)
// ══════════════════════════════════════════════════════════════
function launchConfetti() {
  const canvas = document.createElement('canvas');
  Object.assign(canvas.style, {
    position: 'fixed', inset: '0', width: '100%', height: '100%',
    pointerEvents: 'none', zIndex: '9999',
  });
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;

  const COLORS = ['#7c6de8','#22d3ee','#f472b6','#34d399','#fbbf24'];
  const pieces = Array.from({ length: 80 }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * -canvas.height,
    r: Math.random() * 8 + 4,
    d: Math.random() * 80 + 40,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    tilt: Math.random() * 10 - 10,
    tiltAngle: 0,
    tiltSpeed: Math.random() * 0.1 + 0.05,
  }));

  let frame = 0;
  const max = 100;

  function draw() {
    if (frame > max) { canvas.remove(); return; }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    pieces.forEach(p => {
      p.tiltAngle += p.tiltSpeed;
      p.y += (Math.cos(frame * 0.01 + p.d) + 2 + p.r / 2) * 1.8;
      p.tilt = Math.sin(p.tiltAngle) * 12;

      ctx.beginPath();
      ctx.lineWidth = p.r / 2;
      ctx.strokeStyle = p.color;
      ctx.moveTo(p.x + p.tilt + p.r / 4, p.y);
      ctx.lineTo(p.x + p.tilt, p.y + p.tilt + p.r / 4);
      ctx.stroke();
    });

    frame++;
    requestAnimationFrame(draw);
  }
  draw();
}

// ══════════════════════════════════════════════════════════════
//  SEARCH (for initSearch on /results page status check)
// ══════════════════════════════════════════════════════════════
function initSearch() {
  // On results page, if a search was just run, start polling
  if (window.location.pathname === '/results') return;
}

// ══════════════════════════════════════════════════════════════
//  RESUME UPLOAD
// ══════════════════════════════════════════════════════════════
async function uploadResume(input) {
  const file = input.files?.[0];
  if (!file) return;

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showToast('error', '⚠ Only PDF files are supported.');
    input.value = '';
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    showToast('error', '⚠ File too large. Max 10 MB.');
    input.value = '';
    return;
  }

  // Show progress
  const progress = document.getElementById('resume-progress');
  const progressText = document.getElementById('resume-progress-text');
  if (progress) progress.classList.remove('hidden');
  if (progressText) progressText.textContent = '🤖 Parsing your resume with AI...';

  const formData = new FormData();
  formData.append('resume', file);

  try {
    const resp = await fetch('/api/upload-resume', {
      method: 'POST',
      body: formData,
    });

    const data = await resp.json();

    if (!resp.ok || data.error) {
      throw new Error(data.error || 'Upload failed');
    }

    // Fill form fields from parsed resume
    if (data.name)       setVal('name', data.name);
    if (data.email)      setVal('email', data.email);
    if (data.university) setVal('university', data.university);
    if (data.cgpa)       setVal('cgpa', data.cgpa);
    if (data.bio)        setVal('bio', data.bio);
    if (data.achievements) setVal('achievements', data.achievements);
    if (data.github_url)   setVal('github_url', data.github_url);
    if (data.linkedin_url) setVal('linkedin_url', data.linkedin_url);

    // Degree dropdown
    if (data.degree) {
      const degreeEl = document.getElementById('degree');
      if (degreeEl) {
        const normalized = data.degree.toLowerCase();
        if (normalized.includes('bachelor') || normalized.includes('b.tech') || normalized.includes('b.sc'))
          degreeEl.value = "Bachelor's";
        else if (normalized.includes('master') || normalized.includes('m.tech') || normalized.includes('m.sc'))
          degreeEl.value = "Master's";
        else if (normalized.includes('phd') || normalized.includes('ph.d'))
          degreeEl.value = 'PhD';
      }
    }

    // Projects
    if (data.projects && Array.isArray(data.projects)) {
      setVal('projects', data.projects.join('\n'));
    }

    // Tags: research interests
    const riList   = document.getElementById('research-tags');
    const riHidden = document.getElementById('research_interests');
    if (riList && riHidden && data.research_interests) {
      riList.innerHTML = '';
      riHidden.value = '';
      const interests = Array.isArray(data.research_interests)
        ? data.research_interests
        : String(data.research_interests).split(',');
      interests.filter(Boolean).forEach(t => addTag(t.trim(), riList, riHidden));
    }

    // Tags: skills
    const skList   = document.getElementById('skills-tags');
    const skHidden = document.getElementById('skills');
    if (skList && skHidden && data.skills) {
      skList.innerHTML = '';
      skHidden.value = '';
      const skills = Array.isArray(data.skills)
        ? data.skills
        : String(data.skills).split(',');
      skills.filter(Boolean).forEach(t => addTag(t.trim(), skList, skHidden));
    }

    showToast('success', `📄 Resume parsed! ${data._method === 'ai' ? 'AI extracted' : 'Extracted'} your profile details.`);

  } catch (err) {
    showToast('error', `Resume upload failed: ${err.message}`);
  } finally {
    if (progress) progress.classList.add('hidden');
    input.value = '';  // Reset file input
  }
}

// ══════════════════════════════════════════════════════════════
//  FOLLOW-UP EMAIL
// ══════════════════════════════════════════════════════════════
async function openFollowUp(profId, profName) {
  currentProfId = profId;

  const modal    = document.getElementById('email-modal');
  const subtitle = document.getElementById('modal-prof-name');
  const genArea  = document.getElementById('email-generating');
  const editor   = document.getElementById('email-editor');

  if (!modal) return;

  subtitle.textContent = `Follow-up — Professor ${profName}`;
  genArea.classList.remove('hidden');
  editor.classList.add('hidden');
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  try {
    const resp = await fetch('/api/send-followup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ professor_id: profId, send_now: false }),
    });

    if (!resp.ok) {
      const errData = await resp.json();
      throw new Error(errData.error || 'Failed to generate follow-up');
    }

    const data = await resp.json();

    document.getElementById('email-subject').value = data.subject || '';
    document.getElementById('email-body').value    = data.body    || '';

    const badge = document.getElementById('email-method-badge');
    badge.textContent = '📨 Follow-Up Email';
    badge.style.background = 'hsla(40,90%,55%,0.12)';
    badge.style.color = 'hsl(40, 90%, 55%)';

    genArea.classList.add('hidden');
    editor.classList.remove('hidden');

  } catch (err) {
    closeEmailStudio();
    showToast('error', err.message);
  }
}

// ══════════════════════════════════════════════════════════════
//  INLINE PROFESSOR EMAIL EDITING
// ══════════════════════════════════════════════════════════════
function editProfEmail(profId) {
  const row = document.getElementById(`email-row-${profId}`);
  if (!row) return;

  const currentEmail = document.getElementById(`email-display-${profId}`)?.textContent?.trim() || '';

  row.innerHTML = `
    <div class="email-edit-inline">
      <input type="email" class="form-input form-input-xs" id="email-input-${profId}"
             value="${escHtml(currentEmail)}" placeholder="professor@university.edu"
             onkeydown="if(event.key==='Enter')saveProfEmail(${profId})" />
      <button class="btn btn-primary btn-xs" onclick="saveProfEmail(${profId})">Save</button>
      <button class="btn btn-ghost btn-xs" onclick="location.reload()">Cancel</button>
    </div>
  `;

  document.getElementById(`email-input-${profId}`)?.focus();
}

async function saveProfEmail(profId) {
  const input = document.getElementById(`email-input-${profId}`);
  const email = input?.value?.trim();

  if (!email || !email.includes('@')) {
    showToast('error', '⚠ Please enter a valid email address.');
    return;
  }

  try {
    const resp = await fetch(`/api/professor/${profId}/email`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });

    const data = await resp.json();
    if (data.success) {
      const row = document.getElementById(`email-row-${profId}`);
      row.innerHTML = `
        <span class="prof-email-chip" id="email-display-${profId}">${escHtml(email)}</span>
        <button class="btn-icon-edit" onclick="editProfEmail(${profId})" title="Edit email">✏️</button>
      `;
      showToast('success', `✅ Email updated for professor!`);
    } else {
      showToast('error', data.error || 'Failed to update email.');
    }
  } catch (err) {
    showToast('error', `Error: ${err.message}`);
  }
}

// ══════════════════════════════════════════════════════════════
//  SCROLL REVEAL (IntersectionObserver)
// ══════════════════════════════════════════════════════════════
function initScrollReveal() {
  if (!('IntersectionObserver' in window)) return;

  // Add .reveal class to eligible elements that aren't already animated
  const targets = document.querySelectorAll(
    '.stat-card, .section-card, .recent-card, .top-match-card, ' +
    '.experience-card, .stat-compact, .followup-row, .timeline-item'
  );

  targets.forEach((el, i) => {
    // Skip elements that already have a fade-up animation so we don't double-animate
    if (el.classList.contains('animate-fade-up') ||
        el.classList.contains('animate-fade-up-1') ||
        el.classList.contains('animate-fade-up-2') ||
        el.classList.contains('animate-fade-up-3') ||
        el.classList.contains('animate-fade-up-4')) return;

    el.classList.add('reveal');
    const delayClass = `reveal-delay-${(i % 4) + 1}`;
    el.classList.add(delayClass);
  });

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target); // animate once
        }
      });
    },
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  );

  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
}

// ══════════════════════════════════════════════════════════════
//  DRAG-AND-DROP UPLOAD ZONE
// ══════════════════════════════════════════════════════════════
function initDropZone() {
  const zone = document.getElementById('drop-zone');
  if (!zone) return;

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });

  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));

  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      const input = document.getElementById('resume-upload');
      if (input) {
        // Manually trigger the upload with the dropped file
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        // Call the handler defined in resume.html's block scripts
        if (typeof handleFileSelect === 'function') handleFileSelect(input);
        else if (typeof uploadResume === 'function') uploadResume(input);
      }
    }
  });
}

// ══════════════════════════════════════════════════════════════
//  UTILITIES
// ══════════════════════════════════════════════════════════════
function val(id)      { return document.getElementById(id)?.value?.trim() || ''; }
function setVal(id,v) { const el = document.getElementById(id); if (el) el.value = v ?? ''; }

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}

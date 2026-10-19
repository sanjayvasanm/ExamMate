/**
 * CONFIGURATION: Update this for your environment
 * Render (Cloud): https://YOUR_APP_NAME.onrender.com/api
 * Local: http://10.174.238.113:5000/api
 */
const getApiUrl = () => {
  const override = localStorage.getItem('em_api_override');
  if (override) return override;

  return window.EXAM_MATE_API_URL || 'https://exam-mate-backend-w5t6.onrender.com/api';
};

const API = getApiUrl();

// ── PWA & Performance: Register Service Worker ──────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('../sw.js')
      .then(reg => console.log('[PWA] Service Worker active for mobile optimization.'))
      .catch(err => console.warn('[PWA] Service Worker registration skipped:', err));
  });
}

async function apiFetch(url, options = {}) {
  const token = localStorage.getItem('em_token');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000); // 3m for document processing and AI generation

  const headers = {
    ...options.headers
  };

  if (token && !headers['Authorization']) {
    headers['Authorization'] = 'Bearer ' + token;
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal
    });

    if (res.status === 401) {
      localStorage.clear();
      // Use relative path for login redirect
      const currentPath = window.location.pathname;
      if (!currentPath.includes('login_exam_mate')) {
        window.location.href = '../login_exam_mate/code.html';
      }
      return null;
    }
    return res;
  } catch (e) {
    console.error("[apiFetch Error]", e.name, e.message, "at", url);
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}

function navigate(page) {
  const pages = {
    dashboard: 'dashboard_exam_mate/code.html',
    upload: 'upload_document_exam_mate/code.html',
    ask: 'ask_question_exam_mate/code.html',
    answer: 'answer_exam_mate/code.html',
    history: 'history_exam_mate/code.html',
    profile: 'profile_exam_mate/code.html',
    login: 'login_exam_mate/code.html',
    signup: 'signup_exam_mate/code.html',
    planner: 'planner_exam_mate/code.html',
    quiz: 'quiz_exam_mate/code.html',
    flashcards: 'flashcards_exam_mate/code.html',
    focus: 'focus_exam_mate/code.html'
  };
  // If we are already in a subdirectory (which basically all screens are), go up one level
  const currentPath = window.location.pathname;
  const prefix = (currentPath.includes('_exam_mate') || currentPath.endsWith('folder/')) ? '../' : '';
  window.location.href = prefix + pages[page];
}

function showToast(msg, type = 'error') {
  const t = document.getElementById('toast');
  if (!t) {
    console.warn("Toast element not found:", msg);
    return;
  }
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.className = 'toast', 3500);
}

function enhanceShell() {
  const screen = window.location.pathname.split('/').filter(Boolean).find(part => part.includes('_exam_mate'));
  if (screen) document.body.dataset.screen = screen.replace('_exam_mate', '');
  document.querySelectorAll('header').forEach(header => {
    header.setAttribute('role', 'banner');
    const brand = header.querySelector('h1, [data-brand]');
    if (brand) brand.setAttribute('data-brand', 'Exam Mate');
  });
  document.querySelectorAll('nav.fixed').forEach(nav => {
    nav.setAttribute('aria-label', 'Primary navigation');
  });
  document.body.classList.add('em-ready');
}

document.addEventListener('DOMContentLoaded', enhanceShell);

// Global exposure
window.API = API;
window.apiFetch = apiFetch;
window.getApiUrl = getApiUrl;
window.navigate = navigate;
window.showToast = showToast;
window.enhanceShell = enhanceShell;

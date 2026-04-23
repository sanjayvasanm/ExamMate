/**
 * CONFIGURATION: Update this for your environment
 * Render (Cloud): https://YOUR_APP_NAME.onrender.com/api
 * Local: http://10.174.238.113:5000/api
 */
const RENDER_NAME = 'exammate-ai'; // Change this after you create your Render service

const getApiUrl = () => {
  const override = localStorage.getItem('em_api_override');
  if (override) return override;

  return 'https://exam-mate-backend-w5t6.onrender.com/api';
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
  const timeout = setTimeout(() => controller.abort(), 300000); // 300s (5m) timeout for heavy AI processing

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
    signup: 'signup_exam_mate/code.html'
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

// Global exposure
window.API = API;
window.apiFetch = apiFetch;
window.getApiUrl = getApiUrl;
window.navigate = navigate;
window.showToast = showToast;

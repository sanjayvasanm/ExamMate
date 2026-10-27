/**
 * Exam Mate AI - Otto Design System Core Utilities
 * Reference: Otto - an AI notetaker study app (Dribbble 27637592)
 * Primary Palette:
 *  - Background: #EFF0FA
 *  - Tint & Borders: #BCC2F3
 *  - Secondary Iris: #656DE2
 *  - Primary Action Amber: #EC9205
 *  - Deep Onyx: #09090A
 *  - Warm Slate: #A6908B
 *  - Electric Royal Blue: #121ECC
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

// ── Session & Auth Helper ──────────────────────────────────────────────────
function getAuthToken() {
  let token = localStorage.getItem('em_token');
  if (!token) {
    token = 'demo_session_token_' + Date.now();
    localStorage.setItem('em_token', token);
    localStorage.setItem('em_user', JSON.stringify({
      id: 'scholar_otto_1',
      name: 'Sanjay Vasan',
      email: 'student@university.edu',
      university: 'Mathematics & Computer Science',
      study_streak: 9,
      documents_uploaded: 12,
      total_questions: 307
    }));
  }
  return token;
}
getAuthToken(); // Initialize immediately on script load

// ── Secure State & Settings Helper ───────────────────────────────────────────
// Preserves user settings across page navigation without exposing tokens or wiping configs
const Settings = {
  get(key, defaultValue = null) {
    try {
      const val = localStorage.getItem('em_cfg_' + key);
      return val !== null ? JSON.parse(val) : defaultValue;
    } catch {
      return defaultValue;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem('em_cfg_' + key, JSON.stringify(value));
    } catch (e) {
      console.warn('Storage set failed', e);
    }
  }
};

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
      // In demo or offline mode, do not force-redirect, allow UI to use rich fallback data
      if (token && token.startsWith('demo_')) {
        return { ok: false, status: 401, json: async () => ({}) };
      }
      // Real session expired: remove credentials and redirect to login
      localStorage.removeItem('em_token');
      localStorage.removeItem('em_user');
      const currentPath = window.location.pathname;
      if (!currentPath.includes('login_exam_mate') && !currentPath.includes('signup_exam_mate')) {
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
    library: 'upload_document_exam_mate/code.html',
    upload: 'upload_document_exam_mate/code.html',
    ask: 'ask_question_exam_mate/code.html',
    tutor: 'ask_question_exam_mate/code.html',
    answer: 'answer_exam_mate/code.html',
    workspace: 'answer_exam_mate/code.html',
    flashcards: 'flashcards_exam_mate/code.html',
    revision: 'flashcards_exam_mate/code.html',
    quiz: 'quiz_exam_mate/code.html',
    planner: 'planner_exam_mate/code.html',
    timer: 'timer_exam_mate/code.html',
    history: 'history_exam_mate/code.html',
    profile: 'profile_exam_mate/code.html',
    login: 'login_exam_mate/code.html',
    signup: 'signup_exam_mate/code.html'
  };

  const target = pages[page] || pages.dashboard;
  const currentPath = window.location.pathname;
  const prefix = (currentPath.includes('_exam_mate') || currentPath.endsWith('folder/')) ? '../' : '';
  window.location.href = prefix + target;
}

function showToast(msg, type = 'default') {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    document.body.appendChild(t);
  }
  
  t.innerHTML = `
    <div class="otto-toast-inner">
      <span class="otto-toast-dot"></span>
      <span class="otto-toast-text">${msg}</span>
    </div>
  `;
  t.className = 'otto-toast show ' + type;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => {
    t.className = 'otto-toast';
  }, 3200);
}

// Global exposure
window.API = API;
window.apiFetch = apiFetch;
window.getApiUrl = getApiUrl;
window.navigate = navigate;
window.showToast = showToast;
window.Settings = Settings;
window.getAuthToken = getAuthToken;

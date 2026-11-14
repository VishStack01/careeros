// Load test for Propelo Cloud with k6 (https://k6.io): `k6 run scripts/loadtest.js`.
// Point it at a staging server, never production: BASE=https://staging.example.com k6 run scripts/loadtest.js
// It signs in as test accounts you created first (LOAD_EMAIL like load+{n}@example.com, LOAD_PASSWORD),
// then does what people do most: open the app, read their roles, page through them and check their plan.
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = (__ENV.BASE || 'http://127.0.0.1:8000').replace(/\/$/, '');
const USERS = Number(__ENV.USERS || 20);

export const options = {
  scenarios: {
    browse: { executor: 'ramping-vus', startVUs: 0, stages: [
      { duration: '1m', target: Number(__ENV.VUS || 50) },
      { duration: '3m', target: Number(__ENV.VUS || 50) },
      { duration: '30s', target: 0 },
    ] },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{kind:read}': ['p(95)<400'],
    'http_req_duration{kind:page}': ['p(95)<300'],
  },
};

const H = { 'Content-Type': 'application/json', 'X-CareerOS-CSRF': '1' };

export function setup() {
  const sessions = [];
  for (let i = 0; i < USERS; i++) {
    const email = (__ENV.LOAD_EMAIL || 'load+{n}@example.com').replace('{n}', i);
    const r = http.post(`${BASE}/api/auth/login`, JSON.stringify({ email, password: __ENV.LOAD_PASSWORD || '' }), { headers: H });
    const cookie = r.cookies && Object.values(r.cookies)[0];
    if (r.status === 200 && cookie) sessions.push(`${Object.keys(r.cookies)[0]}=${cookie[0].value}`);
  }
  if (!sessions.length) throw new Error('No test account could sign in. Create them first and set LOAD_EMAIL and LOAD_PASSWORD.');
  return { sessions };
}

export default function (data) {
  const cookie = data.sessions[__VU % data.sessions.length];
  const opt = kind => ({ headers: Object.assign({ Cookie: cookie }, H), tags: { kind } });
  check(http.get(`${BASE}/api/health`, { tags: { kind: 'page' } }), { health: r => r.status === 200 });
  check(http.get(`${BASE}/app`, opt('page')), { app: r => r.status === 200 });
  check(http.get(`${BASE}/api/me`, opt('read')), { me: r => r.status === 200 });
  const jobs = http.get(`${BASE}/api/c/jobs`, opt('read'));
  check(jobs, { jobs: r => r.status === 200 || r.status === 304 });
  check(http.get(`${BASE}/api/billing`, opt('read')), { billing: r => r.status === 200 });
  check(http.get(`${BASE}/api/plans`, { tags: { kind: 'read' } }), { plans: r => r.status === 200 });
  sleep(1 + Math.random() * 3);
}

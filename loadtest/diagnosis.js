// k6 load test (Phase 5.6): concurrent diagnosis sessions, as customers use them, against the API.
// Every step is a non-LLM step (the LLM layer is off: LLM_PROVIDER=none on the target), and each has the threshold
// p95 < 800 ms. Run it with scripts/loadtest.sh (one command, local stack or staging); see README "Phase 5.6".
//
// Env: API_URL (https://api.staging.instantmechanic.online), WEB_ORIGIN (https://diagnose.staging...), VUS (200),
//      DURATION (5m at full load), RAMP (1m), TEXT_SHARE (0.3: share of sessions that also type a description).
import http from "k6/http";
import { check, fail, sleep } from "k6";
import { Counter } from "k6/metrics";

const API = (__ENV.API_URL || "").replace(/\/$/, "");
const ORIGIN = __ENV.WEB_ORIGIN || "";
const VUS = Number(__ENV.VUS || 200);
const TEXT_SHARE = Number(__ENV.TEXT_SHARE || 0.3);
const MAX_ANSWERS = 14;

const STEPS = ["categories", "vehicle_search", "start", "answer", "result", "estimates", "explanations"];
export const sessionsDone = new Counter("diagnosis_sessions_completed");

export const options = {
  scenarios: {
    diagnosis: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: __ENV.RAMP || "1m", target: VUS },
        { duration: __ENV.DURATION || "5m", target: VUS },
        { duration: "30s", target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    // Every step, and each one on its own: 95% answered within 800 ms.
    "http_req_duration{kind:api}": ["p(95)<800"],
    ...Object.fromEntries(STEPS.map((s) => [`http_req_duration{step:${s}}`, ["p(95)<800"]])),
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
  insecureSkipTLSVerify: __ENV.INSECURE === "1", // local stack only (Caddy's own certificate)
  hosts: __ENV.HOST_IP ? { localhost: __ENV.HOST_IP } : undefined, // k6 in Docker reaching the Mac's localhost
};

const TILES = ["wont_start", "pickup_jerking", "overheating_leaks", "ac", "clutch_gearbox", "brakes_steering",
  "suspension_noise", "tyres", "battery_lights", "fuel_cng_diesel"];
const SEARCHES = ["swift 2019 petrol", "creta diesel", "baleno", "nexon", "city 2018", "i20", "wagon r cng", "dzire"];
const TEXTS = ["car not starting in the morning, clicking sound", "gaadi garam ho rahi hai", "AC is not cooling",
  "brake lagate time awaaz aati hai", "clutch hard ho gaya hai", "steering vibrate karta hai high speed pe"];

const pick = (list) => list[Math.floor(Math.random() * list.length)];
const params = (step, extra = {}) => ({
  headers: { "Content-Type": "application/json", Origin: ORIGIN, "X-Request-ID": `k6-${__VU}-${typeof __ITER === "undefined" ? "setup" : __ITER}-${step}` },
  tags: { kind: "api", step },
  ...extra,
});

export function setup() {
  if (!API) fail("set API_URL (scripts/loadtest.sh does)");
  const warm = (step) => ({ ...params(step), tags: { kind: "setup" }, timeout: "120s" });
  const r = http.get(`${API}/api/health/ready`, warm("setup"));
  if (r.status !== 200) fail(`API not ready at ${API}: ${r.status} ${r.body}`);
  // Warm up, not measured: each API process builds its diagnosis engine (and loads the search model) on its first
  // request, as after any restart; a running server is warm. Enough calls to reach every process.
  for (let i = 0; i < 12; i++) {
    http.get(`${API}/api/categories`, warm("warmup"));
    const s = http.get(`${API}/api/vehicles/search?q=swift&limit=1`, warm("warmup"));
    const hit = s.status === 200 && s.json("results") && s.json("results")[0];
    if (hit) {
      http.post(`${API}/api/diagnosis/sessions`, JSON.stringify({ vehicle: { variant_id: hit.variant_id },
        topic_id: "ac", text: "warm up" }), warm("warmup"));
    }
  }
}

export default function () {
  const cats = http.get(`${API}/api/categories`, params("categories"));
  check(cats, { "categories 200": (r) => r.status === 200 });

  const search = http.get(`${API}/api/vehicles/search?q=${encodeURIComponent(pick(SEARCHES))}&limit=8`, params("vehicle_search"));
  check(search, { "search 200": (r) => r.status === 200 });
  const hits = search.status === 200 ? search.json("results") : [];
  if (!hits || !hits.length) return sleep(1);
  sleep(1 + Math.random() * 2); // the customer reads the list

  const body = { vehicle: { variant_id: pick(hits).variant_id }, topic_id: pick(TILES) };
  if (Math.random() < TEXT_SHARE) body.text = pick(TEXTS);
  const start = http.post(`${API}/api/diagnosis/sessions`, JSON.stringify(body), params("start"));
  if (!check(start, { "session started": (r) => r.status === 200 || r.status === 201 })) return sleep(2);
  let turn = start.json();
  const id = turn.session_id;

  for (let n = 0; n < MAX_ANSWERS && turn && !turn.done && turn.question; n++) {
    sleep(2 + Math.random() * 4); // reading the question
    const options = turn.question.options.filter((o) => !o.not_sure);
    const choice = Math.random() < 0.1 || !options.length ? "not_sure" : pick(options).id;
    const ans = http.post(`${API}/api/diagnosis/sessions/${id}/answers`,
      JSON.stringify({ question_id: turn.question.id, option_id: choice }), params("answer"));
    if (!check(ans, { "answer 200": (r) => r.status === 200 })) return;
    turn = ans.json();
  }

  const result = http.get(`${API}/api/diagnosis/sessions/${id}/result`, params("result"));
  check(result, { "result 200": (r) => r.status === 200, "result has a disclaimer": (r) => !!r.json("disclaimer") });
  const est = http.get(`${API}/api/estimates?session_id=${id}`, params("estimates"));
  check(est, { "estimates 200": (r) => r.status === 200 });
  const expl = http.get(`${API}/api/diagnosis/sessions/${id}/explanations`,
    params("explanations", { headers: { Accept: "text/event-stream", Origin: ORIGIN } }));
  check(expl, { "explanations 200": (r) => r.status === 200 });
  sessionsDone.add(1);
  sleep(3 + Math.random() * 5); // reading the result
}

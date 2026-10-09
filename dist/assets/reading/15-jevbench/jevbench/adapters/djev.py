"""djev (Maisa) adapter: typed Noul / Choice / Score answers from a diffusion-gemma model.

Request (documented at https://api.djev.dev/docs, OpenAPI 0.1.0, read 2026-09-19):
  POST {endpoint}/v1/request
  Prefer: low-latency            (documented "direct evaluation" mode)
  {"model": "djev", "state": ..., "questions": {"decision": {type, instructions, criteria}}}
No options are sent, so the documented defaults apply (one step, seed 0).

djev's question types are Jev's: every JevBench record maps 1:1
  noul   answer["noul"] = P(yes)         -> {"yes": p, "no": 1-p}
  choice answer["probabilities"]         -> used as-is (keys = options)
  score  answer["probabilities"]         -> used as-is (keys = level indices)

Auth: a djev API key from the env var named by `key_env` (default DJEV_API_KEY), sent as Bearer.
If DJEV_SESSION_SECRET is set instead, the adapter uses djev's documented five-minute inference
token (GET /v1/access/session), refreshed outside the timed request. Secrets are never logged.

Politeness: one request at a time. 429 / 529 / 503 are answered with the documented
"retry the same bytes after Retry-After", bounded (exponential 2-64 s, above their 1 s hint); a 202 durable receipt is polled at its
Retry-After. Latency is the runner's wall clock, as for every entrant, so any back-off counts
against djev; back-offs are also recorded in `usage["djev_retries"]` / `usage["djev_wait_s"]`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .base import DecisionResult, build_question, http_post_json

RETRY_STATUSES = (429, 503, 529)
MAX_RETRIES = 6
MAX_WAIT_S = 120.0


class DjevAdapter:
    name = "djev"

    def __init__(self, endpoint=None, model=None, key_env="DJEV_API_KEY", timeout_s=120.0,
                 price_input_per_m=None, price_output_per_m=None):
        self.endpoint = (endpoint or "https://api.djev.dev").rstrip("/")
        self.model = model or "djev"
        self.key_env = key_env or "DJEV_API_KEY"
        self.timeout_s = timeout_s
        self.price_input_per_m = price_input_per_m
        self.price_output_per_m = price_output_per_m
        self._token, self._token_exp = None, 0.0

    def build_request(self, task) -> dict:
        return {"model": self.model, "state": task.state, "questions": {"decision": build_question(task)}}

    def _auth(self):
        key = os.environ.get(self.key_env, "")
        if key:
            return key
        session = os.environ.get("DJEV_SESSION_SECRET", "")
        if not session:
            return None
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        req = urllib.request.Request(f"{self.endpoint}/v1/access/session",
                                     headers={"Authorization": f"Bearer {session}"}, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        self._token, self._token_exp = d["access_token"], float(d["expires_at"])
        return self._token

    def _poll(self, url, headers, first_wait):
        """Poll a durable receipt's status URL until it has an answer (bounded)."""
        deadline = time.time() + MAX_WAIT_S
        wait = first_wait
        while time.time() < deadline:
            time.sleep(min(max(wait, 0.5), 10.0))
            req = urllib.request.Request(url if url.startswith("http") else self.endpoint + url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    parsed = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", errors="replace")
            status = parsed.get("status") if isinstance(parsed, dict) else None
            if isinstance(parsed, dict) and ("answers" in parsed or status in ("succeeded", "failed")):
                return 200, parsed.get("result", parsed) if "answers" not in parsed else parsed
            wait = float(parsed.get("retry_after", 1.0)) if isinstance(parsed, dict) else 1.0
        return 504, "durable request not finished within the bounded wait"

    def run(self, task) -> DecisionResult:
        try:
            auth = self._auth()
        except Exception as e:  # session refresh failed
            return DecisionResult(adapter=self.name, ok=False, error=f"auth refresh failed: {type(e).__name__}",
                                  probs_source="native", model=self.model)
        if not auth:
            return DecisionResult(adapter=self.name, ok=False, error=f"missing env key {self.key_env}",
                                  probs_source="native", model=self.model)
        body = self.build_request(task)
        retries, waited = 0, 0.0
        while True:
            headers = {"Authorization": f"Bearer {auth}", "Content-Type": "application/json", "Prefer": "low-latency"}
            try:
                status, parsed, latency = http_post_json(f"{self.endpoint}/v1/request", body, headers, self.timeout_s)
            except ConnectionError as e:
                return DecisionResult(adapter=self.name, ok=False, error=str(e), probs_source="native",
                                      model=self.model, request_body=body)
            if status in RETRY_STATUSES and retries < MAX_RETRIES and waited < MAX_WAIT_S:
                code = (parsed.get("error") or {}).get("code") if isinstance(parsed, dict) else None
                if code in ("insufficient_credits",):
                    break
                ra = 2.0 ** retries * 2.0
                time.sleep(ra)
                retries += 1
                waited += ra
                auth = self._auth() or auth
                continue
            break
        if status == 202 and isinstance(parsed, dict) and parsed.get("status_url"):
            t0 = time.perf_counter()
            status, parsed = self._poll(parsed["status_url"], {"Authorization": f"Bearer {auth}"},
                                        float(parsed.get("retry_after", 1.0)))
            latency += time.perf_counter() - t0
        res = DecisionResult(adapter=self.name, ok=False, status=status, latency_s=latency,
                             probs_source="native", model=self.model, raw=parsed, request_body=body)
        if status != 200 or not isinstance(parsed, dict):
            res.error = f"HTTP {status}: {str(parsed)[:300]}"
            return res
        ans = (parsed.get("answers") or {}).get("decision")
        if not isinstance(ans, dict):
            res.error = "missing 'answers.decision'"
            return res
        res.usage = dict(parsed.get("usage") or {})
        if retries:
            res.usage.update(djev_retries=retries, djev_wait_s=waited)
        res.model = parsed.get("model") or self.model
        qtype = task.question["type"]
        if ans.get("type") != qtype:
            res.error = "answer type mismatch"
            return res
        try:
            if qtype == "noul":
                if isinstance(ans["noul"], bool) or not isinstance(ans["noul"], (int, float)):
                    raise ValueError("noul must be numeric")
                p = float(ans["noul"])
                if not (0.0 <= p <= 1.0):
                    raise ValueError(f"noul out of range: {p}")
                res.probs = {"yes": p, "no": 1.0 - p}
            else:
                if qtype == "choice" and ans.get("choice") not in task.labels:
                    raise ValueError("choice not among the options")
                probs = ans.get("probabilities")
                if not isinstance(probs, dict):
                    raise ValueError(f"{qtype} answer missing probabilities")
                res.probs = probs
        except (KeyError, TypeError, ValueError) as e:
            res.error = f"answer parse failed: {e}"
            return res
        res.ok = True
        return res

    def reserve_estimate(self, task) -> float:
        pin = self.price_input_per_m if self.price_input_per_m is not None else 0.035
        pout = self.price_output_per_m if self.price_output_per_m is not None else 0.0
        return 100_000 * pin / 1e6 + 4_000 * pout / 1e6

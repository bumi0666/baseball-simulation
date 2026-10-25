"""AI 보조 의사결정 모듈 (FA 영입 / 2군 유망주 기용 추천).

- RuleBasedAdvisor : 항상 동작하는 규칙 기반 기본 구현 (외부 호출 없음)
- NNAdvisor        : 시뮬레이션으로 학습한 소형 신경망(ai_model.npz). 없으면 규칙 기반 사용
- LLMAdvisor       : 규칙 기반으로 후보를 추린 뒤 LLM에게 순위·사유를 요청.
                     호출이 실패하거나 응답이 잘못되면 자동으로 규칙 기반 결과로 대체.

LLM 연결은 호출 함수 하나만 넘기면 된다 (키·엔드포인트는 이 모듈이 알지 못함):
    import ai_advisor
    ai_advisor.set_llm(lambda prompt: my_client.complete(prompt))   # str -> str
연결하지 않으면 get_advisor()는 RuleBasedAdvisor를 돌려준다.
"""
import json
import re
from dataclasses import dataclass


@dataclass
class Recommendation:
    player: object
    score: float
    reason: str


# ── 신경망 입력 특징 (학습 스크립트와 게임이 같은 함수를 쓴다) ──────

ATTRS = ["contact", "power", "eye", "run", "defense", "velocity", "control", "stamina", "stuff"]
N_FEATURES = len(ATTRS) * 2 + 1


def _attr_vec(p):
    return [p.attr[a]["cur"] / 100.0 if a in getattr(p, "attr", {}) else 0.0 for a in ATTRS]


def make_features(cand, incumbent):
    """후보 선수와 교체 대상(해당 슬롯 현 주전)의 능력치로 만든 특징 벡터."""
    c = _attr_vec(cand)
    i = _attr_vec(incumbent) if incumbent is not None else [0.0] * len(ATTRS)
    return c + [x - y for x, y in zip(c, i)] + [1.0 if cand.pos == "P" else 0.0]


# ── 공통 유틸 ───────────────────────────────────────────

def _ovr(p):
    try:
        return p.calculate_ovr()
    except Exception:
        return 0


def _pot_gap(p):
    """현재 능력치 평균 대비 잠재력 평균의 차이 (성장 여력)."""
    cur, pot = [], []
    for v in getattr(p, "attr", {}).values():
        if isinstance(v, dict) and "cur" in v and "pot" in v:
            cur.append(v["cur"])
            pot.append(v["pot"])
    if not cur:
        return 0.0
    return (sum(pot) - sum(cur)) / len(cur)


def _age(p):
    try:
        return p.age()
    except Exception:
        return 27


def _roster_at(players, pos):
    return [p for p in players
            if p.pos == pos and p.status.get("roster", "active") == "active"]


def _demand_salary(p):
    return max(p.salary(), int(p.data.get("market_value", 0) * 0.12))


def _best_ovr(players, pos):
    vals = [_ovr(p) for p in _roster_at(players, pos)]
    return max(vals) if vals else 0


def _worst_starter_ovr(players, pos):
    vals = sorted((_ovr(p) for p in _roster_at(players, pos)), reverse=True)
    need = 5 if pos == "P" else 1          # 선발 투수 5명, 야수는 포지션당 1명
    if len(vals) < need:
        return 0
    return vals[need - 1]


# ── 규칙 기반 구현 ──────────────────────────────────────

class RuleBasedAdvisor:
    name = "rule"

    def _gain(self, state, my_players, p, weakest_ovr):
        """후보 p가 현 전력에 더하는 이득 (점수 단위)과 설명문."""
        gain = _ovr(p) - weakest_ovr
        txt = "포지션 공백" if not weakest_ovr else "주전 최저 %d" % weakest_ovr
        if weakest_ovr and gain > 0:
            txt = "주전 최저보다 OVR +%d" % gain
        return gain, txt

    def recommend_fa(self, state, fa_players, my_players, top_n=5):
        wage_room = getattr(state, "wage_budget", 0) - getattr(state, "current_wage", 0)
        recs = []
        for p in fa_players:
            demand = _demand_salary(p)
            ovr, age = _ovr(p), _age(p)
            weakest = _worst_starter_ovr(my_players, p.pos)
            gain, gain_txt = self._gain(state, my_players, p, weakest)
            if gain <= 0 and _pot_gap(p) < 5:
                continue
            score = gain + _pot_gap(p) * (0.8 if age <= 25 else 0.2)
            score -= max(0, age - 32) * 1.5
            burden = demand / max(1, wage_room)
            score -= min(15.0, burden * 2)                      # 연봉 부담(상한 있음)
            if not _roster_at(my_players, p.pos):
                score += 10                                     # 포지션 공백
            reason = f"{p.pos} OVR {ovr}({gain_txt}) · {age}세 · 요구 연봉 임금 여유의 {burden * 100:.0f}%"
            if burden > 1:
                reason += " (예산 초과)"
            recs.append(Recommendation(p, round(score, 1), reason))
        recs.sort(key=lambda r: -r.score)
        return recs[:top_n]

    def recommend_prospects(self, state, my_players, top_n=5):
        recs = []
        for p in my_players:
            if p.status.get("roster", "active") != "inactive":
                continue
            ovr, age = _ovr(p), _age(p)
            weakest = _worst_starter_ovr(my_players, p.pos)
            gain, gain_txt = self._gain(state, my_players, p, weakest)
            ready = gain                                        # 바로 주전급인가
            growth = _pot_gap(p)
            score = ovr + growth * (0.7 if age <= 24 else 0.3) - max(0, age - 27) * 0.5
            score += max(0, ready) * 1.5
            if ready > 0:
                why = f"1군 {p.pos} 공백" if not weakest else f"1군 {p.pos} {gain_txt}"
            else:
                why = f"성장 여력 +{growth:.0f}, 출전 기회를 주면 육성 가능"
            recs.append(Recommendation(p, round(score, 1), f"{p.pos} OVR {ovr} · {age}세 · {why}"))
        recs.sort(key=lambda r: -r.score)
        return recs[:top_n]


# ── 학습된 소형 신경망 (게임 시뮬레이션으로 학습) ─────────

class NNAdvisor(RuleBasedAdvisor):
    """ai_training/ 에서 시뮬레이션으로 학습한 MLP(19→16→8→1)가 '이 선수로 교체했을 때
    경기당 득실차 변화'를 예측한다. 추론은 numpy 행렬곱 몇 번이 전부이며 가중치 파일이
    없으면 생성 시 예외 → get_advisor()가 규칙 기반으로 대체한다."""
    name = "nn"
    SCORE_PER_RUN = 60.0           # 득실차 1점/경기를 규칙 기반 점수 단위로 환산

    def __init__(self, path=None):
        import os
        import numpy as np
        self._np = np
        path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_model.npz")
        m = np.load(path)
        self.m = {k: m[k] for k in m.files}
        if self.m["W1"].shape[0] != N_FEATURES:
            raise ValueError("모델 입력 크기가 맞지 않음")

    def predict_run_gain(self, cand, incumbent):
        np, m = self._np, self.m
        x = (np.array(make_features(cand, incumbent), dtype=np.float64) - m["mu"]) / m["sd"]
        h = np.tanh(np.tanh(x @ m["W1"] + m["b1"]) @ m["W2"] + m["b2"])
        return float((h @ m["W3"] + m["b3"])[0] * m["ys"])

    def _gain(self, state, my_players, p, weakest_ovr):
        inc = getattr(state, "lineup", {}).get(p.pos)
        if inc is None or inc is p:
            return super()._gain(state, my_players, p, weakest_ovr)
        r = self.predict_run_gain(p, inc)
        return r * self.SCORE_PER_RUN, "예상 득실차 %+.2f점/경기" % r


# ── LLM 연동 (교체 가능) ────────────────────────────────

class LLMAdvisor(RuleBasedAdvisor):
    name = "llm"

    def __init__(self, llm_fn, fallback=None):
        self.llm_fn = llm_fn
        self.fallback = fallback or RuleBasedAdvisor()

    def _rerank(self, task, recs, extra=""):
        if len(recs) < 2:
            return recs
        cands = [{"id": r.player.id, "name": r.player.name, "info": r.reason,
                  "rule_score": r.score} for r in recs]
        prompt = (f"야구 구단 GM 보조. 작업: {task}. {extra}\n"
                  "아래 후보를 추천 순으로 정렬해 JSON 배열만 출력: "
                  '[{"id": <id>, "reason": "<한 줄 사유>"}]\n'
                  + json.dumps(cands, ensure_ascii=False))
        try:
            text = self.llm_fn(prompt)
            m = re.search(r"\[.*\]", text, re.S)
            items = json.loads(m.group(0))
            by_id = {r.player.id: r for r in recs}
            out = []
            for i, it in enumerate(items):
                r = by_id.pop(it["id"], None)
                if r:
                    out.append(Recommendation(r.player, float(len(recs) - i), str(it.get("reason", r.reason))))
            if not out:
                return recs
            out.extend(by_id.values())
            return out
        except Exception:
            return recs                                          # 어떤 실패든 규칙 기반으로 대체

    def recommend_fa(self, state, fa_players, my_players, top_n=5):
        base = self.fallback.recommend_fa(state, fa_players, my_players, top_n=max(top_n * 3, 10))
        return self._rerank("FA 영입 우선순위", base,
                            f"임금 여유 {getattr(state, 'wage_budget', 0) - getattr(state, 'current_wage', 0)}")[:top_n]

    def recommend_prospects(self, state, my_players, top_n=5):
        base = self.fallback.recommend_prospects(state, my_players, top_n=max(top_n * 3, 10))
        return self._rerank("2군 유망주 1군 기용 우선순위", base)[:top_n]


_llm_fn = None


def set_llm(fn):
    """fn: str(프롬프트) -> str(응답). None이면 규칙 기반으로 되돌린다."""
    global _llm_fn
    _llm_fn = fn


def _base_advisor():
    try:
        return NNAdvisor()                 # 학습된 모델이 있으면 사용
    except Exception:
        return RuleBasedAdvisor()          # 파일 없음/numpy 없음 등 → 규칙 기반


def get_advisor():
    base = _base_advisor()
    return LLMAdvisor(_llm_fn, fallback=base) if _llm_fn else base

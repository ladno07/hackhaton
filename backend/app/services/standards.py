"""Training standards by the federal standard of sports training (FSSP):
comparison of results with thresholds and readiness to move to the next stage."""

from datetime import date, timedelta
from sqlalchemy import select
from app.models import *
from app.services.ratings import RANKS

# Stages in the order of training; the name is what athletes.training_stage holds.
STAGES = {
    "np": "Этап начальной подготовки",
    "ut": "Учебно-тренировочный этап",
    "ssm": "Этап совершенствования спортивного мастерства",
    "vsm": "Этап высшего спортивного мастерства",
}
SHORT = {"np": "НП", "ut": "УТ", "ssm": "ССМ", "vsm": "ВСМ"}
# rank required in addition to the standards to be transferred to the stage
STAGE_RANKS = {"ssm": "КМС", "vsm": "МС"}
CATEGORIES = {"ofp": "ОФП", "sfp": "СФП"}
SEXES = {"male": "юноши, мужчины", "female": "девушки, женщины"}
# testing is held at least once a year, so an older result does not count
VALID_DAYS = 365


def stage_of(athlete):
    """Stage code of the athlete; unknown free text counts as no stage."""
    name = (athlete.training_stage or "").strip().lower()
    return next((k for k, v in STAGES.items() if v.lower() == name), None)


def next_stage(stage):
    codes = list(STAGES)
    if stage is None:
        return codes[0]
    i = codes.index(stage)
    return codes[i + 1] if i + 1 < len(codes) else None


def meets(standard, value, threshold=None):
    threshold = standard.threshold if threshold is None else threshold
    return value >= threshold if standard.better == "higher" else value <= threshold


def standard_text(s):
    sign = "≥" if s.better == "higher" else "≤"
    return f"{sign} {s.threshold:g} {s.unit}"


def standard_view(db, s):
    discipline = db.get(Discipline, s.discipline_id) if s.discipline_id else None
    return {
        **{
            k: getattr(s, k)
            for k in (
                "id", "stage", "category", "name", "unit", "better", "threshold",
                "sex", "discipline_id", "source", "sort_order", "archived_at",
            )
        },
        "stage_name": STAGES[s.stage],
        "stage_short": SHORT[s.stage],
        "category_name": CATEGORIES[s.category],
        "discipline": discipline.short_name if discipline else None,
        "threshold_text": standard_text(s),
    }


def disciplines_of(db, athlete):
    return set(
        db.scalars(
            select(AthleteDiscipline.discipline_id).where(
                AthleteDiscipline.athlete_id == athlete.id,
                AthleteDiscipline.end_year.is_(None),
            )
        )
    )


def applicable(db, athlete, stage, sex_known=True):
    """Active standards of the stage: common to the sport plus those of the
    disciplines the athlete trains in; by sex unless sex_known is False."""
    sex = athlete.user.sex
    disciplines = disciplines_of(db, athlete)
    return [
        s
        for s in db.scalars(
            select(TrainingStandard)
            .where(TrainingStandard.stage == stage, TrainingStandard.archived_at.is_(None))
            .order_by(
                TrainingStandard.category,
                TrainingStandard.sort_order,
                TrainingStandard.id,
            )
        )
        if (s.discipline_id is None or s.discipline_id in disciplines)
        and (s.sex is None or (s.sex == sex if sex_known else True))
    ]


def best_result(db, athlete_id, standard, today=None):
    """Best attempt within the validity period, compared with the current threshold."""
    today = today or date.today()
    attempts = db.scalars(
        select(StandardResult).where(
            StandardResult.athlete_id == athlete_id,
            StandardResult.standard_id == standard.id,
            StandardResult.tested_on > today - timedelta(days=VALID_DAYS),
        )
    ).all()
    if not attempts:
        return None, 0
    # the best value; among equal ones the latest attempt
    sign = 1 if standard.better == "higher" else -1
    best = max(attempts, key=lambda r: (sign * r.value, r.tested_on))
    return best, len(attempts)


def current_rank(db, athlete_id, today=None):
    today = today or date.today()
    valid = db.scalars(
        select(SportsRank.name).where(
            SportsRank.athlete_id == athlete_id, SportsRank.expires_on >= today
        )
    ).all()
    known = [r for r in valid if r in RANKS]
    return max(known, key=RANKS.index) if known else None


def readiness(db, athlete, today=None):
    """Whether the athlete may be transferred to the next stage now."""
    today = today or date.today()
    stage = stage_of(athlete)
    target = next_stage(stage)
    base = {
        "athlete_id": athlete.id,
        "full_name": athlete.user.full_name,
        "sex": athlete.user.sex,
        "training_stage": athlete.training_stage,
        "stage": stage,
        "stage_name": STAGES.get(stage),
        "target": target,
        "target_name": STAGES.get(target),
        "valid_days": VALID_DAYS,
    }
    if not target:
        return {
            **base, "items": [], "passed": 0, "total": 0, "rank_required": None,
            "rank": current_rank(db, athlete.id, today), "rank_ok": True,
            "blockers": ["Спортсмен на последнем этапе подготовки"],
            "ready": False, "ready_since": None,
        }
    sex_known = athlete.user.sex is not None
    standards = applicable(db, athlete, target, sex_known)
    items = []
    for s in standards:
        if s.sex and not sex_known:
            best, attempts = None, 0
        else:
            best, attempts = best_result(db, athlete.id, s, today)
        items.append(
            {
                **standard_view(db, s),
                "best_value": best.value if best else None,
                "best_on": best.tested_on if best else None,
                "attempts": attempts,
                "met": bool(best and meets(s, best.value)),
            }
        )
    rank = current_rank(db, athlete.id, today)
    required = STAGE_RANKS.get(target)
    rank_ok = not required or bool(rank and RANKS.index(rank) >= RANKS.index(required))
    blockers = []
    if not standards:
        blockers.append("Для этапа нет нормативов в справочнике")
    if not sex_known and any(s.sex for s in standards):
        blockers.append("Не указан пол — нормативы ОФП различаются для юношей и девушек")
    missing = [i for i in items if not i["met"]]
    if missing:
        blockers.append(f"Не выполнено нормативов: {len(missing)} из {len(items)}")
    if not rank_ok:
        blockers.append(f"Нужен разряд не ниже «{required}»")
    if athlete.suspended_until and athlete.suspended_until >= today:
        blockers.append(f"Отстранён до {athlete.suspended_until:%d.%m.%Y}")
    ready = not blockers
    return {
        **base,
        "items": items,
        "passed": len(items) - len(missing),
        "total": len(items),
        "rank_required": required,
        "rank": rank,
        "rank_ok": rank_ok,
        "blockers": blockers,
        "ready": ready,
        # the attempt that completed the set: when the athlete became ready
        "ready_since": max(i["best_on"] for i in items) if ready else None,
    }


def result_view(db, r):
    s = db.get(TrainingStandard, r.standard_id)
    recorder = db.get(User, r.recorded_by) if r.recorded_by else None
    return {
        **{
            k: getattr(r, k)
            for k in (
                "id", "athlete_id", "standard_id", "value", "tested_on", "threshold",
                "passed", "comment", "recorded_role", "created_at",
            )
        },
        "full_name": db.get(Athlete, r.athlete_id).user.full_name,
        "standard": s.name,
        "unit": s.unit,
        "stage": s.stage,
        "stage_short": SHORT[s.stage],
        "category_name": CATEGORIES[s.category],
        "threshold_text": ("≥ " if s.better == "higher" else "≤ ")
        + f"{r.threshold:g} {s.unit}",
        "expired": r.tested_on <= date.today() - timedelta(days=VALID_DAYS),
        "recorded_by_name": recorder.full_name if recorder else None,
    }


def transfer_view(db, t):
    author = db.get(User, t.created_by) if t.created_by else None
    return {
        **{
            k: getattr(t, k)
            for k in (
                "id", "athlete_id", "from_stage", "to_stage", "decided_on",
                "order_number", "basis", "comment", "created_at",
            )
        },
        "full_name": db.get(Athlete, t.athlete_id).user.full_name,
        "to_stage_name": STAGES[t.to_stage],
        "created_by_name": author.full_name if author else None,
    }


def basis_of(state):
    """Snapshot kept with the transfer order."""
    return {
        "standards": [
            {
                "name": i["name"],
                "category": i["category_name"],
                "threshold": i["threshold_text"],
                "value": i["best_value"],
                "unit": i["unit"],
                "tested_on": i["best_on"].isoformat(),
            }
            for i in state["items"]
        ],
        "rank": state["rank"],
        "rank_required": state["rank_required"],
    }

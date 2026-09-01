import calendar as calendar_module
from datetime import date, datetime

from sqlalchemy.orm import Session

from app import models


def build_calendar(db: Session, year: int, month: int) -> list:
    _, days_in_month = calendar_module.monthrange(year, month)
    month_start = datetime(year, month, 1)
    month_end = datetime(year, month, days_in_month, 23, 59, 59)

    events_by_day = {day: [] for day in range(1, days_in_month + 1)}

    posted_logs = (
        db.query(models.PostLog)
        .filter(models.PostLog.posted_at >= month_start, models.PostLog.posted_at <= month_end)
        .all()
    )
    for log in posted_logs:
        gp = log.generated_post
        events_by_day[log.posted_at.day].append(
            {
                "time": log.posted_at.strftime("%H:%M"),
                "platform": gp.platform.value,
                "title": gp.article.title,
                "kind": "posted",
            }
        )

    schedules = (
        db.query(models.Schedule)
        .filter(
            models.Schedule.is_active.is_(True),
            models.Schedule.scheduled_at >= month_start,
            models.Schedule.scheduled_at <= month_end,
        )
        .all()
    )
    for schedule in schedules:
        gp = schedule.generated_post
        events_by_day[schedule.scheduled_at.day].append(
            {
                "time": schedule.scheduled_at.strftime("%H:%M"),
                "platform": gp.platform.value,
                "title": gp.article.title,
                "kind": "scheduled",
            }
        )

    cal = calendar_module.Calendar(firstweekday=6)  # 日曜始まり
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_cells = []
        for day in week:
            if day == 0:
                week_cells.append(None)
            else:
                week_cells.append(
                    {
                        "day": day,
                        "weekday": date(year, month, day).weekday(),  # 0=月 ... 6=日
                        "events": events_by_day[day],
                    }
                )
        weeks.append(week_cells)

    return weeks

"""DB 초기화 및 집계 해석 통합 검증."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import METHOD_AUTO, METHOD_UNSUBMITTED, TZ  # noqa: E402
from db import (  # noqa: E402
    authenticate,
    determine_apply_method,
    ensure_login_accounts,
    get_connection,
    import_employees_from_csv,
    init_schema,
    list_employees,
    materialize_missing_applications,
    resolve_applications_for_date,
    seed_sample_auto_reservations,
    upsert_daily_application,
)
from config import SAMPLE_EMPLOYEE_CSV  # noqa: E402


def test_db_flow(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    conn = get_connection(db_file)
    init_schema(conn)
    added = import_employees_from_csv(conn, SAMPLE_EMPLOYEE_CSV)
    assert added >= 10
    ensure_login_accounts(conn)
    user = authenticate(conn, "황태연", "1111", "에이텍컴퓨터")
    assert user is not None
    assert user["name"] == "황태연"
    assert user["affiliate"] == "에이텍컴퓨터"
    assert authenticate(conn, "황태연", "1111", "에이텍오토") is None
    seed_sample_auto_reservations(conn)

    employees = list_employees(conn)
    by_name = {(row["name"], row["department"]): row for row in employees}
    hwang = by_name[("황태연", "생산관리팀")]
    park = by_name[("박지훈", "생산관리팀")]

    wednesday = date(2026, 9, 16)
    after_lunch = datetime(2026, 9, 16, 9, 0, tzinfo=TZ)
    resolved = resolve_applications_for_date(conn, wednesday)
    resolved_map = {row["employee_id"]: row for row in resolved}

    assert resolved_map[hwang["id"]]["lunch"] == 1
    assert resolved_map[hwang["id"]]["apply_method"] == METHOD_AUTO
    assert resolved_map[park["id"]]["lunch"] == 0
    assert resolved_map[park["id"]]["apply_method"] == METHOD_UNSUBMITTED

    upsert_daily_application(conn, park, wednesday, 1, 0, "수동변경", "2026-09-16T08:00:00")
    created = materialize_missing_applications(conn, wednesday, after_lunch)
    assert created >= 1

    again = resolve_applications_for_date(conn, wednesday)
    again_map = {row["employee_id"]: row for row in again}
    assert again_map[park["id"]]["lunch"] == 1
    assert again_map[park["id"]]["apply_method"] == "수동변경"
    assert again_map[hwang["id"]]["source"] == "saved"
    assert again_map[hwang["id"]]["apply_method"] == METHOD_AUTO

    assert determine_apply_method({"lunch": 1, "dinner": 0}, 1, 0) == METHOD_AUTO
    assert determine_apply_method({"lunch": 1, "dinner": 0}, 1, 1) == "수동변경"
    conn.close()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        test_db_flow(Path(folder))
    print("db tests passed")

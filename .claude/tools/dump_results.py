"""Read-only dump of Portal results for given events -> JSON on stdout.
Run on server with the app venv:  .venv/bin/python dump_results.py 13 14
"""
import json
import sys

from wsgi import app
from app.models import Event, Result, ResultImport
from app.extensions import db


def dump(event_ids):
    out = {"events": []}
    for eid in event_ids:
        ev = Event.query.get(eid)
        if not ev:
            out["events"].append({"id": eid, "missing": True})
            continue
        # neuester Import pro Event
        imports = (
            ResultImport.query.filter_by(event_id=eid)
            .order_by(ResultImport.id.desc())
            .all()
        )
        imports_meta = [
            {"id": ri.id, "created_at": str(ri.created_at), "final": ri.final,
             "n": Result.query.filter_by(result_import_id=ri.id).count()}
            for ri in imports
        ]
        latest_id = imports[0].id if imports else None
        rows = (
            Result.query.filter_by(result_import_id=latest_id).all()
            if latest_id else []
        )
        out["events"].append(
            {
                "id": ev.id,
                "name": ev.name,
                "external_id": ev.external_id,
                "ais": getattr(ev, "ais_turniernummer", None),
                "imports": imports_meta,
                "latest_import_id": latest_id,
                "n_results": len(rows),
                "results": [
                    {
                        "id": r.id,
                        "import_id": r.result_import_id,
                        "ring": r.ring,
                        "discipline": r.discipline,
                        "category_code": r.category_code,
                        "class_level": r.class_level,
                        "run_no": r.run_no,
                        "lic": r.registration_external_id,
                        "start_no": r.start_no,
                        "rank": r.rank,
                        "time_s": r.time_s,
                        "faults": r.faults,
                        "refusals": r.refusals,
                        "total_faults": r.total_faults,
                        "eliminated": r.eliminated,
                        "status": r.status,
                        "dog": r.dog_name,
                        "handler": r.handler_name,
                    }
                    for r in rows
                ],
            }
        )
    return out


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]] or [13, 14]
    with app.app_context():
        print(json.dumps(dump(ids), ensure_ascii=False, default=str))

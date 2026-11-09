"""Apply result corrections on the server (ORM, inside app context).

  .venv/bin/python apply_corrections.py backup
  .venv/bin/python apply_corrections.py <eid> dry
  .venv/bin/python apply_corrections.py <eid> commit

Reads corrections_<eid>.json (list of {id, dog, set:{field:value}}).
Writes a per-row before-image to rowbackup_<eid>_<ts>.json before committing.
"""
import gzip, json, os, subprocess, sys, tempfile
from datetime import datetime
from urllib.parse import urlparse, unquote

from wsgi import app
from app.extensions import db
from app.models import Result

FIELDS = ["rank", "time_s", "faults", "refusals", "total_faults", "eliminated", "status"]
BACKDIR = "/home/xahizivi/backups"


def backup_table():
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    u = urlparse(uri)
    user, pw = unquote(u.username or ""), unquote(u.password or "")
    host, port = u.hostname or "localhost", u.port or 3306
    dbname = (u.path or "").lstrip("/")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKDIR, exist_ok=True)
    cnf = tempfile.NamedTemporaryFile("w", delete=False, suffix=".cnf")
    cnf.write(f"[client]\nuser={user}\npassword={pw}\nhost={host}\nport={port}\n")
    cnf.close()
    os.chmod(cnf.name, 0o600)
    out = os.path.join(BACKDIR, f"results_backup_{ts}.sql.gz")
    try:
        p = subprocess.run(
            ["mysqldump", f"--defaults-extra-file={cnf.name}", dbname, "results"],
            stdout=subprocess.PIPE, check=True,
        )
        with gzip.open(out, "wb") as f:
            f.write(p.stdout)
    finally:
        os.unlink(cnf.name)
    print("backup written:", out, os.path.getsize(out), "bytes")


def apply(eid, commit):
    with open(f"corrections_{eid}.json", encoding="utf-8") as fh:
        corr = json.load(fh)
    rowbackup = []
    for c in corr:
        r = db.session.get(Result, c["id"])
        if r is None:
            print("!! MISSING id", c["id"]); continue
        before = {f: getattr(r, f) for f in FIELDS}
        rowbackup.append({"id": c["id"], "before": before, "set": c["set"]})
        print(f"id={c['id']:6} {c['dog']}/{c['handler']}")
        for k, v in c["set"].items():
            print(f"     {k}: {getattr(r, k)!r} -> {v!r}")
            setattr(r, k, v)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKDIR, exist_ok=True)
    bpath = os.path.join(BACKDIR, f"rowbackup_{eid}_{ts}.json")
    with open(bpath, "w", encoding="utf-8") as fh:
        json.dump(rowbackup, fh, ensure_ascii=False, indent=2, default=str)
    print(f"before-image: {bpath} ({len(rowbackup)} rows)")
    if commit:
        db.session.commit()
        print(f"COMMITTED {len(rowbackup)} rows for event {eid}")
    else:
        db.session.rollback()
        print("DRY-RUN (rolled back, no changes persisted)")


if __name__ == "__main__":
    with app.app_context():
        if sys.argv[1] == "backup":
            backup_table()
        else:
            eid = int(sys.argv[1])
            apply(eid, commit=(len(sys.argv) > 2 and sys.argv[2] == "commit"))

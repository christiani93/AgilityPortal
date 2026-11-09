import sys
from wsgi import app
from app.models import Event
from app.blueprints.admin.routes_results_export import build_tkamo_csv

eid = int(sys.argv[1]) if len(sys.argv) > 1 else 14
with app.app_context():
    ev = Event.query.get(eid)
    sys.stdout.write(build_tkamo_csv(ev))

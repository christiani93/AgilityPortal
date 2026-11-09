"""Reconcile Portal results (dump JSON) against official XLSX ground truth.
Usage: reconcile.py <dump.json> <event_id> <xlsx_path>
Prints per-field diffs keyed by (discipline, category, class, license).
"""
import json, re, sys, collections
import openpyxl


def norm_lic(x):
    if x is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(x)).upper()


def load_xlsx(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    idx = {h: i for i, h in enumerate(hdr)}
    out = {}
    for r in rows[1:]:
        disc = r[idx["Lauf"]]
        cat = r[idx["Kategorie"]]
        kl = str(r[idx["Klasse"]])
        lic = norm_lic(r[idx["Lizenznummer"]])
        dis = (r[idx["Disqualifiziert"]] == "DIS")
        gf = r[idx["Gesamtfehler"]]
        gf = None if gf in (None, "") else float(gf)
        rec = {
            "rank": r[idx["Rang"]],
            "time": r[idx["Laufzeit"]],
            "faults": None if r[idx["Fehler"]] is None else int(r[idx["Fehler"]]) // 5,
            "refusals": None if r[idx["Verweigerung"]] is None else int(r[idx["Verweigerung"]]) // 5,
            "total_faults": gf,
            "dis": dis,
            "dog": r[idx["Hundename"]],
            "handler": r[idx["Hundefuehrer"]],
        }
        key = (disc, cat, kl, lic)
        if key in out:
            print("  !! DUPLICATE XLSX KEY", key)
        out[key] = rec
    return out


def load_portal(dumppath, eid):
    d = json.load(open(dumppath, encoding="utf-8"))
    ev = [e for e in d["events"] if e["id"] == eid][0]
    out = {}
    for r in ev["results"]:
        key = (r["discipline"], r["category_code"], str(r["class_level"]), norm_lic(r["lic"]))
        if key in out:
            print("  !! DUPLICATE PORTAL KEY", key, r["dog"])
        out[key] = r
    return out, ev


def approx(a, b, tol=0.005):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def main():
    dump, eid, xlsx = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    X = load_xlsx(xlsx)
    P, ev = load_portal(dump, eid)
    print(f"Portal rows={len(P)}  XLSX rows={len(X)}  (event {eid}, import {ev['latest_import_id']})")

    only_portal = [k for k in P if k not in X]
    only_xlsx = [k for k in X if k not in P]
    print(f"\nOnly in Portal ({len(only_portal)}):")
    for k in sorted(only_portal):
        print("   ", k, "status=", P[k]["status"], P[k]["dog"], P[k]["handler"])
    print(f"\nOnly in XLSX ({len(only_xlsx)}):")
    for k in sorted(only_xlsx):
        print("   ", k, X[k]["dog"], X[k]["handler"])

    print("\nField diffs (keys in both):")
    diffs = []
    for k in sorted(P.keys() & X.keys()):
        p, x = P[k], X[k]
        p_dis = bool(p["eliminated"])
        problems = []
        if p_dis != x["dis"]:
            problems.append(f"DIS portal={p_dis} xlsx={x['dis']}")
        if not x["dis"]:
            if p["rank"] != x["rank"]:
                problems.append(f"rank {p['rank']}->{x['rank']}")
            if not approx(p["time_s"], x["time"]):
                problems.append(f"time {p['time_s']}->{x['time']}")
            if (p["faults"] or 0) != (x["faults"] or 0):
                problems.append(f"faults {p['faults']}->{x['faults']}")
            if (p["refusals"] or 0) != (x["refusals"] or 0):
                problems.append(f"refusals {p['refusals']}->{x['refusals']}")
            if not approx(p["total_faults"], x["total_faults"]):
                problems.append(f"totfaults {p['total_faults']}->{x['total_faults']}")
        if problems:
            diffs.append((k, p, x, problems))
            print(f"  {k} [{p['dog']}/{p['handler']}] id={p['id']}")
            for pr in problems:
                print("       -", pr)
    print(f"\nTOTAL rows with diffs: {len(diffs)}")


if __name__ == "__main__":
    main()

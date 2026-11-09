"""Generate the correction set for an event by reconciling Portal dump vs XLSX.
Writes corrections_<eid>.json = list of {id, dog, set:{field:value,...}, reason}.
Non-DIS rows: mirror XLSX rank/time/faults/refusals/total_faults + recomputed grade.
DIS rows (XLSX Disqualifiziert): eliminated=True, status='DIS', rank=None, total_faults=999.0
          (time_s/faults/refusals kept per Portal convention).
"""
import json, re, sys
import openpyxl


def norm_lic(x):
    return re.sub(r"[^A-Za-z0-9]", "", str(x)).upper() if x is not None else ""


def grade(tf):
    if tf is None:
        return None
    if tf == 0:
        return "V0"
    if tf < 6:
        return "V"
    if tf < 16:
        return "SG"
    if tf < 26:
        return "G"
    return "NB"


def load_xlsx(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    idx = {h: i for i, h in enumerate(rows[0])}
    out = {}
    for r in rows[1:]:
        key = (r[idx["Lauf"]], r[idx["Kategorie"]], str(r[idx["Klasse"]]), norm_lic(r[idx["Lizenznummer"]]))
        gf = r[idx["Gesamtfehler"]]
        out[key] = {
            "rank": r[idx["Rang"]],
            "time": r[idx["Laufzeit"]],
            "faults": None if r[idx["Fehler"]] is None else int(r[idx["Fehler"]]) // 5,
            "refusals": None if r[idx["Verweigerung"]] is None else int(r[idx["Verweigerung"]]) // 5,
            "total_faults": None if gf in (None, "") else float(gf),
            "dis": r[idx["Disqualifiziert"]] == "DIS",
        }
    return out


def approx(a, b, tol=0.005):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def main():
    dump, eid, xlsx = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    X = load_xlsx(xlsx)
    d = json.load(open(dump, encoding="utf-8"))
    ev = [e for e in d["events"] if e["id"] == eid][0]
    corr = []
    for r in ev["results"]:
        key = (r["discipline"], r["category_code"], str(r["class_level"]), norm_lic(r["lic"]))
        x = X.get(key)
        if not x:
            continue  # DNS etc. -> not in official export, leave as is
        setf = {}
        if x["dis"]:
            if not r["eliminated"]:
                setf["eliminated"] = True
            if r["status"] != "DIS":
                setf["status"] = "DIS"
            if r["rank"] is not None:
                setf["rank"] = None
            if not approx(r["total_faults"], 999.0):
                setf["total_faults"] = 999.0
            reason = "DIS laut offizieller Rangliste"
        else:
            if r["rank"] != x["rank"]:
                setf["rank"] = x["rank"]
            if not approx(r["time_s"], x["time"]):
                setf["time_s"] = x["time"]
            if (r["faults"] or 0) != (x["faults"] or 0):
                setf["faults"] = x["faults"]
            if (r["refusals"] or 0) != (x["refusals"] or 0):
                setf["refusals"] = x["refusals"]
            if not approx(r["total_faults"], x["total_faults"]):
                setf["total_faults"] = x["total_faults"]
            g = grade(x["total_faults"])
            if g and r["status"] != g and ("total_faults" in setf or "faults" in setf):
                setf["status"] = g
            reason = "Werte an offizielle Rangliste angeglichen"
        if setf:
            corr.append({"id": r["id"], "dog": r["dog"], "handler": r["handler"],
                         "key": key, "set": setf, "reason": reason})
    json.dump(corr, open(f"corrections_{eid}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"event {eid}: {len(corr)} rows to correct")
    for c in corr:
        print(f"  id={c['id']:6} {c['dog']}/{c['handler']}  {c['set']}")


if __name__ == "__main__":
    main()

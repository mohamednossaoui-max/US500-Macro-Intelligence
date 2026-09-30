from __future__ import annotations
import argparse, json
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).with_name("autonomy_source_registry_v1.json")


def load_registry(path=DEFAULT_REGISTRY):
    obj=json.loads(Path(path).read_text(encoding="utf-8"))
    nodes=obj.get("nodes", [])
    ids=[n["id"] for n in nodes]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate node id")
    known=set(ids)
    for n in nodes:
        missing=set(n.get("depends_on", []))-known
        if missing: raise ValueError(f"{n['id']} has unknown dependencies: {sorted(missing)}")
        if not n.get("outputs"): raise ValueError(f"{n['id']} has no declared outputs")
        if not (n.get("workflow") or n.get("command")): raise ValueError(f"{n['id']} has no runner")
    return obj


def topo(nodes):
    by={n["id"]:n for n in nodes}; done=[]; remaining=set(by)
    while remaining:
        ready=sorted(x for x in remaining if set(by[x].get("depends_on",[]))<=set(done))
        if not ready: raise ValueError("dependency graph contains a cycle")
        done.extend(ready); remaining-=set(ready)
    return done


def affected(nodes, changed):
    by={n["id"]:n for n in nodes}; selected=set(changed)
    unknown=selected-set(by)
    if unknown: raise ValueError(f"unknown changed nodes: {sorted(unknown)}")
    grew=True
    while grew:
        grew=False
        for n in nodes:
            if n["id"] not in selected and set(n.get("depends_on",[])) & selected:
                selected.add(n["id"]); grew=True
    return [x for x in topo(nodes) if x in selected]


def dry_run(registry, changed):
    nodes=registry["nodes"]; by={n["id"]:n for n in nodes}
    plan=affected(nodes, changed)
    return [{"order":i+1,"id":x,"runner":by[x].get("workflow") or by[x].get("command"),
             "criticality":by[x]["criticality"],"outputs":by[x]["outputs"]} for i,x in enumerate(plan)]


def main():
    ap=argparse.ArgumentParser(description="Dependency-aware dry-run planner; does not execute or publish.")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY)); ap.add_argument("--changed", nargs="+", required=True)
    ap.add_argument("--json", action="store_true"); args=ap.parse_args()
    reg=load_registry(args.registry); plan=dry_run(reg,args.changed)
    if args.json: print(json.dumps({"dry_run":True,"schedules_enabled":reg["policy"]["schedules_enabled"],"plan":plan},indent=2))
    else:
        print("AUTONOMY DRY RUN — NO WORKFLOWS EXECUTED — NO PUBLICATION")
        for p in plan: print(f"{p['order']:02d}. {p['id']}: {p['runner']}")

if __name__ == "__main__": main()

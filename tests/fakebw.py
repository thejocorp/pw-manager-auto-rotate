#!/usr/bin/env python3
"""A stand-in for the Bitwarden CLI, for the tests: the same commands pwrotate uses, with the
vault kept in the JSON file named by $FAKEBW_STATE."""
import base64, json, os, sys, uuid

state_file = os.environ["FAKEBW_STATE"]
st = json.load(open(state_file))
args = [a for a in sys.argv[1:]]
if "--session" in args:
    i = args.index("--session"); del args[i:i + 2]
st.setdefault("calls", []).append(args)


def save():
    json.dump(st, open(state_file, "w"))


def opt(name):
    return args[args.index(name) + 1] if name in args else None


cmd = args[:2]
if args == ["--version"]:
    print("2026.9.0")
elif args[0] == "status":
    print(json.dumps({"serverUrl": st.get("server"), "userEmail": "ops@example.com",
                      "lastSync": "2026-10-23T00:00:00.000Z", "status": st.get("status", "unlocked")}))
elif args[0] == "sync":
    print("Syncing complete.")
elif cmd == ["list", "organizations"]:
    print(json.dumps(st.get("orgs", [])))
elif cmd == ["list", "org-collections"]:
    print(json.dumps([c for c in st.get("collections", []) if c["organizationId"] == opt("--organizationid")]))
elif cmd == ["list", "items"]:
    q, org = opt("--search"), opt("--organizationid")
    print(json.dumps([it for it in st.get("items", []) if q in it["name"] and (org is None or it.get("organizationId") == org)]))
elif args[0] == "encode":
    sys.stdout.write(base64.b64encode(sys.stdin.read().encode()).decode())
elif cmd == ["create", "item"]:
    it = json.loads(base64.b64decode(sys.stdin.read())); it["id"] = str(uuid.uuid4())
    st.setdefault("items", []).append(it); save(); print(json.dumps(it))
elif cmd == ["edit", "item"]:
    it = json.loads(base64.b64decode(sys.stdin.read()))
    st["items"] = [it if x["id"] == args[2] else x for x in st["items"]]; save(); print(json.dumps(it))
else:
    sys.exit(f"fakebw: unknown command {args}")
save()

#!/usr/bin/env python3
"""Compare direct host inventories; retain unknowns and disabled items."""
import argparse
import json
from audit import write_private


def compare(local, cloud):
    result = {"schema_version": 1, "local_audit_available": bool(local), "parity_verified": False, "items": []}
    if not local:
        result["blockers"] = ["Direct Mac audit unavailable; cloud exposure cannot establish local installations, disabled items or private custom skills."]
        return result
    for section in ["plugins", "skills", "mcp_servers", "development_tools"]:
        index = {}
        for row in cloud.get(section, []):
            index.setdefault(row["name"], []).append(row)
        for row in local.get(section, []):
            matches = index.get(row["name"], [])
            status = "needs_review"
            if row.get("enabled") is False:
                status = "preserve_disabled"
            elif section == "development_tools" and not row.get("present"):
                status = "not_a_local_requirement"
            elif not matches:
                status = "missing" if section == "development_tools" or section == "skills" else "not_observed_in_cloud"
            elif section == "development_tools":
                target = matches[0]
                if not row.get("present"):
                    status = "not_a_local_requirement"
                elif not target.get("present") or target.get("runnable") is False:
                    status = "missing_or_unusable"
                elif row.get("version") == target.get("version") and row.get("version") != "unknown":
                    status = "same_version_workflow_unverified"
                else:
                    status = "version_or_runtime_review"
            elif section == "skills":
                status = "same_source_workflow_unverified" if row.get("sha256") and any(x.get("sha256") == row["sha256"] for x in matches) else "source_review_needed"
            result["items"].append({"category": section, "name": row["name"], "status": status,
                                    "cloud_candidates": len(matches), "connection_verified": False})
    result["blockers"] = ["Run actual user workflows; metadata similarity does not establish end-to-end parity."]
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local")
    p.add_argument("--cloud", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    local = json.load(open(args.local)) if args.local else None
    cloud = json.load(open(args.cloud))
    write_private(args.output, compare(local, cloud))
    print(f"Wrote {args.output}; parity remains unverified until workflows pass.")

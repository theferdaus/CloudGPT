#!/usr/bin/env python3
"""Compare the detailed Mac migration audit without treating caches as installations."""
import argparse
from collections import Counter
import json
from pathlib import Path
from audit import write_private


def compare_mac(mac, filesystem, host):
    plugins, skills, servers, tools = [], [], [], []
    account = host["account_installed_plugins"]
    by_id = {x["id"]: x for x in account}
    by_name = {x["name"].casefold(): x for x in account}
    builtin = {x["name"].casefold(): x for x in filesystem["skills"]}
    special = {"browser": "cloud_browser_alternative_mac_session_not_shared", "chrome": "cloud_browser_alternative_mac_session_not_shared",
               "computer-use": "linux_desktop_alternative", "unified-computer-use": "linux_desktop_alternative",
               "codex-app-tools": "host_tools_partial_scope", "latex": "compile_tool_available_plugin_version_not_compared",
               "computer-history": "mac_history_bound", "messages": "mac_device_bound", "record-and-replay": "host_specific_runtime_not_reproduced"}
    for identity in mac["plugin_identities"]:
        physical = [x for x in mac["plugins"] if x["reference"] == identity["reference"]]
        ids = [(x.get("api_dependency_metadata") or {}).get("source_plugin_id") for x in physical]
        match = next((by_id[x] for x in ids if x in by_id), by_name.get(identity["display_name"].casefold()))
        short = identity["reference"].split("@")[0]
        status = "installation_unverified_do_not_auto_enable"
        if identity.get("state") == "disabled":
            status = "preserve_disabled"
        elif match:
            status = "account_plugin_present_workflow_unverified"
        elif short in builtin:
            status = "bundled_skill_available_version_not_compared"
        elif short in special:
            status = special[short]
        plugins.append({**identity, "local_installation_api_confirmed": any(x.get("installed_api") is True for x in physical),
                        "status": status, "cloud_account_plugin": match.get("name") if match else None,
                        "cloud_connection_probe": match.get("connection_status", "unknown") if match else "unknown",
                        "cloud_version": "unknown", "exact_version_parity": "not_verified"})
    catalog = {}
    for x in host["cloud_skills"]:
        plugin_id = x["package"].split("/")[2]
        catalog[(plugin_id, x["name"].split(":")[-1])] = x["name"]
    public_names = {x["name"].split(":")[-1] for x in host["cloud_skills"]}
    for x in mac["skills"]:
        owner = next((p for p in sorted(mac["plugins"], key=lambda p: len(p.get("root") or ""), reverse=True)
                      if p.get("root") and x.get("skill_file", "").startswith(p["root"] + "/")), None)
        pid = ((owner or {}).get("api_dependency_metadata") or {}).get("source_plugin_id")
        match = catalog.get((pid, x["name"]))
        scope = x.get("scope")
        if x.get("locally_managed_migration_candidate") and scope in ["codex_user", "agents_user", "claude_user"]:
            status = "source_files_required"
        elif scope == "copilot_user":
            status = "alias_preserved_in_audit_target_source_required"
        elif scope == "project_or_archive":
            status = "project_or_archive_not_installed_source_required_if_used"
        elif match:
            status = "same_plugin_skill_catalogued_content_not_compared"
        elif x["name"].casefold() in builtin:
            status = "bundled_skill_alternative_content_not_compared"
        elif scope == "vendor_cache":
            status = "available_vendor_cache_not_proven_installed"
        elif scope == "initial_cache_observation_unavailable":
            status = "source_unavailable_in_mac_export"
        elif x["name"] in public_names:
            status = "same_skill_name_source_identity_unverified"
        else:
            status = "host_skill_or_catalog_gap_needs_review"
        skills.append({"name": x["name"], "scope": scope, "source": x.get("skill_file"), "source_sha256": x.get("sha256"),
                       "local_plugin": owner["reference"] if owner else None, "cloud_skill": match, "status": status})
    service_aliases = {"google calendar": "Google Calendar", "gmail": "Gmail", "mobbin": "Mobbin", "stripe": "Stripe", "vercel": "Vercel", "clickup": "ClickUp"}
    mac_servers = {"node_repl", "computer-use", "event-stream", "messages", "computer-history"}
    for x in mac["mcp_servers"]:
        name, origin = x["name"], x["origin"]
        status = "declaration_only_runtime_not_verified"
        alternative = None
        if x.get("enabled_explicit") is False:
            status = "preserve_disabled_source_definition"
        elif name in ["wavespeed", "notebooklm"] and origin in ["codex_user", "other_agent_or_project"]:
            status = "portable_package_setup_and_probe_required"
        elif name in service_aliases and service_aliases[name].casefold() in by_name:
            status = "account_connector_alternative_protocol_scope_not_identical"
            alternative = service_aliases[name]
        elif name in mac_servers:
            status = "mac_runtime_or_device_bound"
            if name == "node_repl":
                alternative = "managed cloud cua_repl; Mac desktop/browser access remains separate"
        elif name == "cua_repl":
            status = "managed_cloud_cua_alternative"
        servers.append({"name": name, "source": x["source"], "origin": origin, "plugin_reference": x.get("plugin_reference"),
                        "transport": x["transport"], "enabled_explicit": x.get("enabled_explicit"), "status": status,
                        "alternative": alternative, "source_login_verified": False})
    cloud_tools = {x["name"]: x for x in filesystem["development_tools"]}
    for x in mac["development"]["tools"]:
        c = cloud_tools.get(x["name"])
        local_version = x.get("version_probe", {}).get("stdout", "unknown").splitlines()[0]
        status = "not_a_local_path_requirement" if not x.get("on_path") else "cloud_tool_not_in_baseline_probe"
        if x.get("runtime_available") is False:
            status = "local_launcher_has_no_runtime"
        elif x.get("on_path") and c:
            status = "cloud_missing_or_unusable" if not c["present"] or c["runnable"] is False else "available_version_or_workflow_review"
        tools.append({"name": x["name"], "local_on_path": x.get("on_path"), "local_version": local_version,
                      "cloud_present": c["present"] if c else "not_probed", "cloud_version": c["version"] if c else "unknown", "status": status})
    return {"schema_version": 2, "local_audit_received": True, "local_audit_time": mac["audit_time"], "no_capability_loss_verified": False,
            "evidence_limits": mac["coverage"]["limits"], "local_summary": mac["summary"],
            "plugins": plugins, "skills": skills, "mcp_definitions": servers, "development_tools": tools,
            "summary": {section: dict(Counter(x["status"] for x in rows)) for section, rows in [("plugins", plugins), ("skills", skills), ("mcp_definitions", servers), ("development_tools", tools)]},
            "remaining_gates": ["Transfer actual managed skill sources with hashes; this audit contains manifests only.",
                                "Review divergent copies and Mac paths before deployment.", "Verify actual project workflows with their source code and inputs.",
                                "Complete required cloud logins; source declarations do not prove Mac OAuth sessions were active.",
                                "Confirm custom skill/MCP discovery in a new cloud agent session and publish reusable environment settings."]}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local", required=True)
    p.add_argument("--cloud-filesystem", required=True)
    p.add_argument("--cloud-host", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = compare_mac(json.load(open(a.local)), json.load(open(a.cloud_filesystem)), json.load(open(a.cloud_host)))
    write_private(a.output, result)
    print(json.dumps(result["summary"], indent=2))

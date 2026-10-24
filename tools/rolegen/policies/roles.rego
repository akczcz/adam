# Jedna Rego politika pro všechny role (package authz – data rolí jsou v data.roles.<role> z build/opa/data.json, rolegen). Používá ji gateway extAuthz, hook Agent SDK
# (PreToolUse) i PEP paměti. Vstup: {role, tool:{server, action}, http:{path, method, service}, memory:{op, scope, type, sensitivity}, tenant, input_flags}
package authz

import rego.v1

role_def := data.roles[input.role]

default decision := {"allow": false, "reason": "no_rule"}

dangerous if {
	some f in input.input_flags
	f in role_def.deny_tool_inputs
}

# --- MCP nástroje ---------------------------------------------------------------------------------------------------
decision := {"allow": false, "reason": "unknown_role"} if { not role_def }

decision := {"allow": false, "reason": "tool_denied"} if {
	role_def
	input.tool
	input.tool.action in role_def.mcp[input.tool.server].deny
}

decision := {"allow": true, "reason": "tool_allowed", "with_approval": false} if {
	role_def
	input.tool
	not dangerous
	not input.tool.action in role_def.mcp[input.tool.server].deny
	input.tool.action in role_def.mcp[input.tool.server].allow
}

decision := {"allow": true, "reason": "tool_requires_approval", "with_approval": true} if {
	role_def
	input.tool
	not dangerous
	input.tool.action in role_def.mcp[input.tool.server].with_approval
}

# Nebezpečné vstupy nástrojů (Bash.dangerouslyDisableSandbox) – deny bez ohledu na allow list
decision := {"allow": false, "reason": "dangerous_tool_input"} if {
	role_def
	dangerous
}

# --- git přes gateway ------------------------------------------------------------------------------------------------
decision := {"allow": false, "reason": "receive_pack_forbidden"} if {
	role_def
	input.http
	endswith(input.http.path, "/git-receive-pack")
	some h in role_def.http
	h.route == input.http.service
	h.receive_pack == "none"
}

decision := {"allow": false, "reason": "receive_pack_protected_branch"} if {
	role_def
	input.http
	endswith(input.http.path, "/git-receive-pack")
	some h in role_def.http
	h.route == input.http.service
	h.receive_pack == "branches"
	input.http.branch in {"main", "release"}
}

decision := {"allow": true, "reason": "git_allowed"} if {
	role_def
	input.http
	some h in role_def.http
	h.route == input.http.service
	input.http.method in h.methods
	startswith(input.http.path, replace(h.path_prefix, "{tenant}", input.tenant))
	not endswith(input.http.path, "/git-receive-pack")
}

decision := {"allow": true, "reason": "git_push_branch"} if {
	role_def
	input.http
	endswith(input.http.path, "/git-receive-pack")
	some h in role_def.http
	h.route == input.http.service
	h.receive_pack == "branches"
	not input.http.branch in {"main", "release"}
	startswith(input.http.path, replace(h.path_prefix, "{tenant}", input.tenant))
}

# --- paměť -----------------------------------------------------------------------------------------------------------
sens_rank := {"public": 0, "internal": 1, "confidential": 2, "personal": 3}

decision := {"allow": true, "reason": "memory_read"} if {
	role_def
	input.memory.op == "read"
	some r in role_def.memory.read
	r.scope == input.memory.scope
	input.memory.type in r.types
	sens_rank[input.memory.sensitivity] <= sens_rank[r.sensitivity_max]
}

decision := {"allow": true, "reason": "memory_propose", "effective_status": "proposed"} if {
	role_def
	input.memory.op == "write"
	input.memory.scope in role_def.memory.write.scopes
	input.memory.type in role_def.memory.write.types
}

decision := {"allow": true, "reason": "memory_approve"} if {
	role_def
	input.memory.op == "approve"
	role_def.memory.approve.enabled == true
	input.memory.scope in role_def.memory.approve.scopes
	input.memory.type in role_def.memory.approve.types
	sens_rank[input.memory.sensitivity] <= sens_rank[role_def.memory.approve.sensitivity_max]
}

decision := {"allow": false, "reason": "memory_forget_human_only"} if {
	role_def
	input.memory.op == "forget"
}

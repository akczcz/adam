# Harness M1 – politika paměti pro OPA (REST /v1/data/memory/decision).
# Vstup: {action, token:{tenant_id, roles, sub, agent_id}, record:{scope, status, tenant_id}, requested_status}
package memory

import rego.v1

default decision := {"allow": false, "reason": "no_rule", "effective_status": "rejected"}

human if "human" in input.token.roles
reviewer if "reviewer" in input.token.roles
agent if "agent" in input.token.roles

# Čtení: vždy jen vlastní tenant (filtr vynucuje server z tokenu, OPA jen potvrdí).
decision := {"allow": true, "reason": "search_own_tenant", "effective_status": ""} if {
	input.action == "search_memory"
	input.token.tenant_id != ""
}

# Zápis: agent smí vždy jen `proposed`, i když žádá `approved` (karanténa).
decision := {"allow": true, "reason": "agent_write_quarantined", "effective_status": "proposed"} if {
	input.action == "create_memory"
	agent
	not human
	input.record.tenant_id == input.token.tenant_id
}

# Člověk smí zapsat rovnou approved ve scope zákazník/firma.
decision := {"allow": true, "reason": "human_write", "effective_status": input.requested_status} if {
	input.action == "create_memory"
	human
	input.record.tenant_id == input.token.tenant_id
	input.requested_status in {"proposed", "approved"}
}

# Schválení: jen reviewer nebo člověk téhož tenanta; agent nikdy.
decision := {"allow": true, "reason": "approve_by_reviewer", "effective_status": "approved"} if {
	input.action == "approve_memory"
	input.record.tenant_id == input.token.tenant_id
	some r in input.token.roles
	r in {"reviewer", "human"}
}

# Zapomenutí zdroje (GDPR výmaz): jen člověk.
decision := {"allow": true, "reason": "forget_by_human", "effective_status": "tombstoned"} if {
	input.action == "forget_source"
	human
}

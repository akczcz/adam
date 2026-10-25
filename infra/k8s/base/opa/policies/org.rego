# Harness O-1 – PDP nevratných akcí (knowledge/organization/autonomie.md, N1 merge, N2 deploy).
# Vstup: {action, actor:{role, spiffe_id}, zakazka_id, artifact_hash, approval:{token, by, artifact_hash, action, exp}}
# Podpis approval tokenu ověřuje PEP (HMAC jako zástupce OpenBao transit) a dává `approval.valid`.
package org

import rego.v1

default decision := {"allow": false, "reason": "no_rule"}

# Agentní role NIKDY neprovádí nevratnou akci – ani se schválením (agent navrhuje, workflow provádí).
decision := {"allow": false, "reason": "agent_role_cannot_execute_irreversible"} if {
	input.action in {"merge", "deploy"}
	input.actor.role in {"vyvojar", "reviewer", "architekt", "account", "sre"}
}

# merge-executor / deploy-executor (deterministická Dapr aktivita) smí jen s platným schválením
# vázaným na týž artefakt (hash), tutéž akci a tutéž zakázku, do expirace, od člověka.
decision := {"allow": true, "reason": "executor_with_valid_approval"} if {
	input.action in {"merge", "deploy"}
	input.actor.role == sprintf("%s-executor", [input.action])
	input.approval.valid == true
	input.approval.action == input.action
	input.approval.artifact_hash == input.artifact_hash
	input.approval.zakazka_id == input.zakazka_id
	input.approval.by_kind == "human"
	input.approval.exp > input.now
	not input.zakazka.stopped
}

decision := {"allow": false, "reason": "zakazka_stopped"} if {
	input.action in {"merge", "deploy"}
	input.zakazka.stopped
}

decision := {"allow": false, "reason": "approval_not_by_human"} if {
	input.action in {"merge", "deploy"}
	startswith(input.actor.role, input.action)
	input.approval.valid == true
	input.approval.artifact_hash == input.artifact_hash
	input.approval.by_kind != "human"
	not input.zakazka.stopped
}

decision := {"allow": false, "reason": "approval_artifact_mismatch"} if {
	input.action in {"merge", "deploy"}
	startswith(input.actor.role, input.action)
	input.approval.valid == true
	input.approval.artifact_hash != input.artifact_hash
	not input.zakazka.stopped
}

decision := {"allow": false, "reason": "approval_expired"} if {
	input.action in {"merge", "deploy"}
	startswith(input.actor.role, input.action)
	input.approval.valid == true
	input.approval.artifact_hash == input.artifact_hash
	input.approval.by_kind == "human"
	input.approval.exp <= input.now
	not input.zakazka.stopped
}

# Reverzibilní akce agentů: push na větev zakázky ano, jinam ne.
decision := {"allow": true, "reason": "branch_push"} if {
	input.action == "push_branch"
	input.actor.role == "vyvojar"
	startswith(input.branch, sprintf("zakazka/%s/", [input.zakazka_id]))
}

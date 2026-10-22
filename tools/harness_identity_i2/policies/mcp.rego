# Harness I2 – politika pro OPA-Envoy za agentgateway extAuthz.
# Vstup: JSON-RPC tělo (input.parsed_body) + JWT claims, které gateway posílá
# ve filter_metadata["envoy.filters.http.jwt_authn"].jwt_payload.
package envoy.authz

import rego.v1

default allow := false

# OPA-Envoy 1.21.2 předává AttributeContext v camelCase (metadataContext.filterMetadata),
# dokumentace uvádí snake_case – čteme obojí. Ověřeno 2026-10-22 z decision logu.
jwt := object.get(input.attributes, ["metadataContext", "filterMetadata", "envoy.filters.http.jwt_authn", "jwt_payload"],
	object.get(input.attributes, ["metadata_context", "filter_metadata", "envoy.filters.http.jwt_authn", "jwt_payload"], {}))

method := object.get(input, ["parsed_body", "method"], "")

tool := object.get(input, ["parsed_body", "params", "name"], "")

allow if {
	method != "tools/call"
	object.get(jwt, "sub", "") != ""
}

allow if {
	method == "tools/call"
	tool == "lookup_ticket"
	object.get(jwt, "sub", "") != ""
}

denied_tool if tool == "delete_ticket"

reason := "denied_tool" if denied_tool

reason := "allow" if {
	not denied_tool
	allow
}

reason := "no_rule" if {
	not denied_tool
	not allow
}

result := {
	"allowed": allow,
	"http_status": 403,
	"body": sprintf("tool %q denied for %q", [tool, object.get(jwt, "sub", "")]),
	"dynamic_metadata": {
		"decision": allow,
		"tool": tool,
		"sub": object.get(jwt, "sub", ""),
		"reason": reason,
	},
}

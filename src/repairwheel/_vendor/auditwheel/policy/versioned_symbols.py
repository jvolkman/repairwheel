from __future__ import annotations

import logging

from . import load_policies

log = logging.getLogger(__name__)


def versioned_symbols_policy(versioned_symbols: dict[str, set[str]]) -> int:
    def policy_is_satisfied(
        policy_name: str, policy_sym_vers: dict[str, set[str]]
    ) -> bool:
        policy_satisfied = True
        for name in set(required_vers) & set(policy_sym_vers):
            if not required_vers[name].issubset(policy_sym_vers[name]):
                for symbol in required_vers[name] - policy_sym_vers[name]:
                    log.debug(
                        "Package requires %s, incompatible with "
                        "policy %s which requires %s",
                        symbol,
                        policy_name,
                        policy_sym_vers[name],
                    )
                policy_satisfied = False
        return policy_satisfied

    required_vers: dict[str, set[str]] = {}
    for symbols in versioned_symbols.values():
        for symbol in symbols:
            sym_name, _, _ = symbol.partition("_")
            required_vers.setdefault(sym_name, set()).add(symbol)
    matching_policies: list[int] = []
    for p in load_policies():
        policy_sym_vers = {
            sym_name: {sym_name + "_" + version for version in versions}
            for sym_name, versions in p["symbol_versions"].items()
        }
        if policy_is_satisfied(p["name"], policy_sym_vers):
            matching_policies.append(p["priority"])

    if len(matching_policies) == 0:
        # the base policy (generic linux) should always match
        raise RuntimeError("Internal error")

    return max(matching_policies)

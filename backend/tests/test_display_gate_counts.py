from signals.retail_action_payload import display_gate_counts


def test_counts_primary_gates_only():
    gates = [{"id": "valuation", "pass": False}, {"id": "regime", "pass": True},
             {"id": "momentum", "pass": True}, {"id": "ml", "pass": True}, {"id": "confidence", "pass": False}]
    assert display_gate_counts(gates) == {"gates_passed": 3, "gates_total": 4}


def test_falls_back_to_all_and_handles_empty():
    assert display_gate_counts([{"id": "x", "pass": True}]) == {"gates_passed": 1, "gates_total": 1}
    assert display_gate_counts(None) == {"gates_passed": 0, "gates_total": 4}

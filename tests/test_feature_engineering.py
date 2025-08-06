from utils.data import build_llm_features


def test_build_llm_features_keys():
    data = build_llm_features("SPY")
    expected = {"vwap_deviation_pct", "atm_delta", "atm_oi", "dealer_gamma_$"}
    assert expected.issubset(data.keys())

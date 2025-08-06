from utils.llm import LLMClient


def test_system_prompt_contains_new_rules():
    import os

    os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
    client = LLMClient(model="gpt-4o-mini")
    prompt = client._get_system_prompt()
    # Ensure new rules are present
    assert "dealer_gamma_$" in prompt
    assert "last two trades" in prompt or "last trade was WIN" in prompt

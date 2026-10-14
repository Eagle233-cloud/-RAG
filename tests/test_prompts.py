from app.prompts import DEFAULT_PROMPT, PROMPT_PRESETS, preset_payload


def test_prompt_presets_include_expected_roles():
    keys = {item["key"] for item in preset_payload()}
    assert {"default", "interviewer", "teacher", "analyst"} <= keys
    assert DEFAULT_PROMPT == PROMPT_PRESETS["default"]["prompt"]


def test_prompt_presets_have_names_and_prompts():
    for preset in preset_payload():
        assert preset["name"]
        assert preset["prompt"]

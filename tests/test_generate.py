from rag.generate import DEFAULT_MODEL_ID, _build_converse_kwargs, _extract_answer


def test_build_converse_kwargs_sets_temperature_not_top_p():
    kwargs = _build_converse_kwargs(
        model_id=DEFAULT_MODEL_ID, system_prompt="sys", user_prompt="usr",
        temperature=0.4, max_tokens=400,
    )
    # Claude 4+ rejects temperature AND topP together -- only one may be set.
    assert kwargs["inferenceConfig"]["temperature"] == 0.4
    assert "topP" not in kwargs["inferenceConfig"]


def test_build_converse_kwargs_has_model_and_messages():
    kwargs = _build_converse_kwargs(
        model_id="some-model", system_prompt="SYS TEXT", user_prompt="USR TEXT",
        temperature=0.2, max_tokens=100,
    )
    assert kwargs["modelId"] == "some-model"
    assert kwargs["system"] == [{"text": "SYS TEXT"}]
    assert kwargs["messages"] == [{"role": "user", "content": [{"text": "USR TEXT"}]}]
    assert kwargs["inferenceConfig"]["maxTokens"] == 100


def test_extract_answer_parses_converse_response():
    response = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Subject: Come back!\nBody: ...\nRationale: ..."}],
            }
        },
        "stopReason": "end_turn",
    }
    assert _extract_answer(response) == "Subject: Come back!\nBody: ...\nRationale: ..."

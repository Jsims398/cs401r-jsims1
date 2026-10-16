"""Bedrock Converse call for offer generation.

Uses the cross-region inference profile ("us." prefix) -- Claude 4.5+
cannot be invoked on-demand by its bare model ID. Sets temperature only,
never temperature AND topP together: Claude 4+ models reject that
combination with ValidationException.
"""

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _build_converse_kwargs(model_id: str, system_prompt: str, user_prompt: str,
                            temperature: float, max_tokens: int) -> dict:
    return {
        "modelId": model_id,
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {
            "temperature": temperature,
            "maxTokens": max_tokens,
        },
    }


def _extract_answer(response: dict) -> str:
    return response["output"]["message"]["content"][0]["text"]


def generate_offer(system_prompt: str, user_prompt: str,
                    model_id: str = DEFAULT_MODEL_ID, region: str = "us-east-1",
                    temperature: float = 0.4, max_tokens: int = 400) -> str:
    import boto3
    client = boto3.client("bedrock-runtime", region_name=region)
    kwargs = _build_converse_kwargs(model_id, system_prompt, user_prompt, temperature, max_tokens)
    response = client.converse(**kwargs)
    return _extract_answer(response)

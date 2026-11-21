import os

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.settings import ModelSettings


MODEL_SETTINGS = ModelSettings(
    timeout=300, max_tokens=8192, thinking=False,
    extra_body={"thinking": {"type": "disabled"}},
)


def model_from_env() -> OpenAIChatModel:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("请设置 DEEPSEEK_API_KEY。")
    provider = DeepSeekProvider(api_key=key, base_url=os.getenv("DEEPSEEK_BASE_URL"))
    return OpenAIChatModel(os.getenv("DEEPSEEK_MODEL", "deepseek-flash"), provider=provider)

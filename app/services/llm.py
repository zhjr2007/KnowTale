from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.BAILIAN_API_KEY,
            base_url=settings.BAILIAN_BASE_URL,
        )
    return _client


async def chat_completion(
    messages: list[dict],
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    client = get_client()
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    resp = await client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=full_messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def embed_text(text: str, model: str | None = None) -> list[float]:
    client = get_client()
    resp = await client.embeddings.create(
        model=model or settings.EMBEDDING_MODEL,
        input=text,
    )
    return resp.data[0].embedding


async def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    client = get_client()
    resp = await client.embeddings.create(
        model=model or settings.EMBEDDING_MODEL,
        input=texts,
    )
    resp.data.sort(key=lambda x: x.index)
    return [d.embedding for d in resp.data]

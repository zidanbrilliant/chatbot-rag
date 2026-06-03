from groq import Groq

from app.config import GROQ_API_KEY, GROQ_MODEL


_client = None


def get_groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def generate_response(system_prompt: str, context: str, history: str, query: str) -> str:
    client = get_groq()
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    if history:
        messages.append({"role": "user", "content": f"Previous conversation:\n{history}"})
    if context:
        messages.append({"role": "user", "content": f"Reference context:\n{context}"})
    messages.append({"role": "user", "content": query})

    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
    )
    return completion.choices[0].message.content

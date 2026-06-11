import json
import re

import ollama


class LLM:
    def __init__(
        self,
        model_name="qwen2.5:7b-instruct",
        num_ctx=8192,
        temperature=0,
    ):
        self.model_name = model_name
        self.num_ctx = num_ctx
        self.temperature = temperature

        print(f"[LLM] Ollama model: {model_name}")
        print(f"[LLM] num_ctx: {num_ctx}")

    def inference(self, text, max_tokens=256):
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": str(text),
                    }
                ],
                options={
                    "temperature": self.temperature,
                    "num_predict": max_tokens,
                    "num_ctx": self.num_ctx,
                },
            )

            return response["message"]["content"].strip()

        except Exception as e:
            print(f"[LLM] inference failed: {e}")
            return ""

    def inference_json(self, text, default=None, max_tokens=256):
        if default is None:
            default = {}

        output = self.inference(
            text=text,
            max_tokens=max_tokens,
        )

        if output == "":
            return default

        try:
            return json.loads(output)

        except json.JSONDecodeError:
            return self._extract_json(output, default)

    def _extract_json(self, text, default):
        match = re.search(r"\{.*\}", str(text), re.DOTALL)

        if match is None:
            return default

        try:
            return json.loads(match.group(0))

        except json.JSONDecodeError:
            return default

def main():
    pass


if __name__ == "__main__":
    main()

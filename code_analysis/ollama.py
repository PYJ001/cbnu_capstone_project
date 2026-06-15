def ask_ollama(prompt, model="deepseek-coder-v2:16b", timeout=300):
    try:
        import requests
    except ImportError:
        return None

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        return f"Ollama 보고서 생성 실패: {e}\n\n로컬 분석 결과를 대신 사용하세요."

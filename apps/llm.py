from openai import OpenAI
from ollama import chat, ChatResponse
from transformers import pipeline
from dotenv import load_dotenv

SUMMARY_INSTRUCTIONS = """You are an academic scholar and researcher with years of professional research experience. You are proficient in all fields, particularly in STEM. You will be given text extracted from a research paper's HTML page, so some figures and images may be absent although their captions may remain. Summarize the problem, methods, and results, including enough relevant detail for a reader to discuss and apply the paper's methods and findings without reading the original. Preserve mathematical notation as LaTeX. Wrap inline math in $...$ and display math in $$...$$ so it can be rendered by KaTeX. Return only the summary."""

class LLMClient():
    def __init__(self):
        load_dotenv()

    def summarize(self, text):
        ...

    def caption(self, image, text=""):
        ...


class OpenAIClient(LLMClient):
    def __init__(self):
        super().__init__()
        self.client = OpenAI()
    
    def summarize(self, text):
        response = self.client.responses.create(
                model="gpt-5",
                reasoning={"effort":"low"},
                instructions=SUMMARY_INSTRUCTIONS,
                input=f"Paper Text: {text}"
        )
        print(response.output_text)
        return response.output_text

class HFClient(LLMClient):
    def __init__(self):
        super().__init__()
        self.client = pipeline("text-generation", model="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", trust_remote_code=True)

    
    def summarize(self, text):
        messages = [
                {"role":"system", "content": SUMMARY_INSTRUCTIONS},
                {"role":"user", "content": f"Paper Text: {text}"}
        ]
        response = self.client(messages)
        print(response[0].get('generated_text', [])[-1])
        return response[0]['generated_text'][-1]['content']

class OllamaClient(LLMClient):
    def __init__(self):
        super().__init__()
    
    def summarize(self, text):
        print("text:", text)
        messages = [
            {"role":"system", "content": SUMMARY_INSTRUCTIONS},
            {"role":"user", "content": f"Paper Text: {text}"}
        ]
        response: ChatResponse = chat(model="qwen:latest", messages=messages)
        print(response['message']['content'])
        return response.message.content

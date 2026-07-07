# list_models.py
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

for model in client.models.list():
    print(model.name, "-> supports:", model.supported_actions)


# output
# (.xane_indicator) PS C:\Xane Funds\indicator> python -u "c:\Xane Funds\indicator\apiSupported Models check.py"
# models/gemini-2.5-flash -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.5-pro -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.0-flash -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.0-flash-001 -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.0-flash-lite-001 -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.0-flash-lite -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.5-flash-preview-tts -> supports: ['countTokens', 'generateContent']
# models/gemini-2.5-pro-preview-tts -> supports: ['countTokens', 'generateContent', 'batchGenerateContent']
# models/gemma-4-26b-a4b-it -> supports: ['generateContent', 'countTokens']
# models/gemma-4-31b-it -> supports: ['generateContent', 'countTokens']
# models/gemini-flash-latest -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-flash-lite-latest -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-pro-latest -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.5-flash-lite -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.5-flash-image -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-3-pro-preview -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-3-flash-preview -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-3.1-pro-preview -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-3.1-pro-preview-customtools -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-3.1-flash-lite-preview -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-3.1-flash-lite -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-3-pro-image-preview -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-3-pro-image -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/nano-banana-pro-preview -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-3.1-flash-image-preview -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-3.1-flash-image -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-3.1-flash-lite-image -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-3.5-flash -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-omni-flash-preview -> supports: ['generateContent', 'countTokens']
# models/lyria-3-clip-preview -> supports: ['generateContent', 'countTokens']
# models/lyria-3-pro-preview -> supports: ['generateContent', 'countTokens']
# models/gemini-3.1-flash-tts-preview -> supports: ['generateContent', 'countTokens', 'batchGenerateContent']
# models/gemini-robotics-er-1.5-preview -> supports: ['generateContent', 'countTokens']
# models/gemini-robotics-er-1.6-preview -> supports: ['generateContent', 'countTokens', 'createCachedContent', 'batchGenerateContent']
# models/gemini-2.5-computer-use-preview-10-2025 -> supports: ['generateContent', 'countTokens']
# models/antigravity-preview-05-2026 -> supports: ['generateContent', 'countTokens']
# models/deep-research-max-preview-04-2026 -> supports: ['generateContent', 'countTokens']
# models/deep-research-preview-04-2026 -> supports: ['generateContent', 'countTokens']
# models/deep-research-pro-preview-12-2025 -> supports: ['generateContent', 'countTokens']
# models/gemini-embedding-001 -> supports: ['embedContent', 'countTextTokens', 'countTokens', 'asyncBatchEmbedContent']
# models/gemini-embedding-2-preview -> supports: ['embedContent', 'countTextTokens', 'countTokens', 'asyncBatchEmbedContent']
# models/gemini-embedding-2 -> supports: ['embedContent', 'countTextTokens', 'countTokens', 'asyncBatchEmbedContent']
# models/aqa -> supports: ['generateAnswer']
# models/imagen-4.0-generate-001 -> supports: ['predict']
# models/imagen-4.0-ultra-generate-001 -> supports: ['predict']
# models/imagen-4.0-fast-generate-001 -> supports: ['predict']
# models/veo-3.1-generate-preview -> supports: ['predictLongRunning']
# models/veo-3.1-fast-generate-preview -> supports: ['predictLongRunning']
# models/veo-3.1-lite-generate-preview -> supports: ['predictLongRunning']
# models/gemini-2.5-flash-native-audio-latest -> supports: ['countTokens', 'bidiGenerateContent']
# models/gemini-2.5-flash-native-audio-preview-09-2025 -> supports: ['countTokens', 'bidiGenerateContent']
# models/gemini-2.5-flash-native-audio-preview-12-2025 -> supports: ['countTokens', 'bidiGenerateContent']
# models/gemini-3.1-flash-live-preview -> supports: ['bidiGenerateContent']
# models/gemini-3.5-live-translate-preview -> supports: ['bidiGenerateContent']
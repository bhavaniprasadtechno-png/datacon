# Keep in sync with packages/shared-types/src/chat.ts's AVAILABLE_LLM_MODELS
# — that's the picker shown in chat; this is what a per-request model
# override gets validated against before being handed to LiteLLM.
AVAILABLE_MODELS = {
    "gemini/gemini-2.5-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemma-4-31b-it",
}

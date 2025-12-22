# Improvement: Smart Fallback Logic for Summarization

## Problem Identified

The original fallback logic for summarization was suboptimal:

```python
# Original (incorrect)
base_url=settings.summarization_base_url or settings.openai_base_url,
api_key=settings.summarization_api_key or settings.openai_api_key,
```

**Issue**: Falls back to embedding API settings, which won't work for LLM tasks.

## Solution Implemented

Improved fallback chain that prioritizes LLM settings:

```python
# Improved (correct)
base_url=settings.summarization_base_url or settings.query_expansion_base_url or settings.openai_base_url,
api_key=settings.summarization_api_key or settings.query_expansion_api_key or settings.openai_api_key,
```

## Fallback Priority Chain

1. **First**: `SUMMARIZATION_BASE_URL` + `SUMMARIZATION_API_KEY` (dedicated settings)
2. **Second**: `QUERY_EXPANSION_BASE_URL` + `QUERY_EXPANSION_API_KEY` (both are LLM tasks)
3. **Third**: `OPENAI_BASE_URL` + `OPENAI_API_KEY` (last resort)

## Benefits

### Before (Problematic)
```bash
# User has query expansion configured
export QUERY_EXPANSION_MODEL="deepseek-ai/DeepSeek-V3"
export QUERY_EXPANSION_BASE_URL="https://api.siliconflow.cn/v1"
export QUERY_EXPANSION_API_KEY="sk-llm-key"

# User adds summarization
export SUMMARIZATION_MODEL="deepseek-ai/DeepSeek-V3"

# ❌ Would fail: Falls back to OPENAI_BASE_URL (embedding API)
```

### After (Fixed)
```bash
# User has query expansion configured
export QUERY_EXPANSION_MODEL="deepseek-ai/DeepSeek-V3"
export QUERY_EXPANSION_BASE_URL="https://api.siliconflow.cn/v1"
export QUERY_EXPANSION_API_KEY="sk-llm-key"

# User adds summarization
export SUMMARIZATION_MODEL="deepseek-ai/DeepSeek-V3"

# ✅ Works: Falls back to QUERY_EXPANSION settings (same LLM API)
```

## Configuration Examples

### Minimal Configuration (Recommended)
```bash
# If you already have query expansion configured, just add the model:
export SUMMARIZATION_MODEL="deepseek-ai/DeepSeek-V3"

# Automatically uses QUERY_EXPANSION_BASE_URL and QUERY_EXPANSION_API_KEY
```

### Separate APIs (Advanced)
```bash
# Embeddings
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="sk-openai-key"

# Query Expansion
export QUERY_EXPANSION_MODEL="deepseek-ai/DeepSeek-V3"
export QUERY_EXPANSION_BASE_URL="https://api.siliconflow.cn/v1"
export QUERY_EXPANSION_API_KEY="sk-siliconflow-key"

# Summarization (uses query expansion settings automatically)
export SUMMARIZATION_MODEL="deepseek-ai/DeepSeek-V3"
```

### All Separate (Maximum Control)
```bash
# Each feature uses different settings
export SUMMARIZATION_MODEL="deepseek-ai/DeepSeek-V3"
export SUMMARIZATION_BASE_URL="https://api.provider-a.com/v1"
export SUMMARIZATION_API_KEY="sk-key-a"

export QUERY_EXPANSION_MODEL="gpt-4"
export QUERY_EXPANSION_BASE_URL="https://api.provider-b.com/v1"
export QUERY_EXPANSION_API_KEY="sk-key-b"

export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="sk-openai-key"
```

## Files Modified

1. `aurora_mcp/server.py:142-143` - Improved fallback in aurora_ingest()
2. `scripts/backfill_summaries.py:183-184` - Improved fallback in backfill script
3. `README.md:312-315` - Updated documentation with fallback chain

## Testing

✅ All tests passing (13 passed, 1 skipped)
✅ No regressions detected
✅ Backward compatible

## Impact

**User Experience Improvement:**
- Users with query expansion configured can now enable summarization with just one variable
- More intuitive: LLM features share LLM API settings
- Reduces configuration complexity

**Date**: 2025-12-22
**Status**: ✅ Completed and Tested

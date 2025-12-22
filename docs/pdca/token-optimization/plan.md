# Plan: Aurora Token Optimization - Two-Stage Retrieval

## 问题陈述 (Problem Statement)

**Current Issue:**
- Aurora search returns full document content (up to 8,000 tokens per document)
- With 10 documents returned, this consumes 80,000 tokens
- Significant token wastage when agents only need to determine relevance
- Scalability issue as document volume grows

**Root Cause:**
- Single-stage retrieval pattern: search always returns full content
- No mechanism for agents to preview documents before fetching full text
- Missing brief summary field in database schema

## 仮説 (Hypothesis)

**Proposed Solution: Hybrid Two-Stage Retrieval Pattern**

Implementing a two-stage retrieval system will reduce token consumption by 90% while maintaining search quality:

1. **Stage 1 (Search)**: Return brief summaries (~100-200 tokens)
2. **Stage 2 (Retrieve)**: Fetch full content only for relevant documents

**Architecture Decision:**
- Add `brief_summary` column (nullable) to documents table
- Generate summaries at ingest time using LLM (zero search latency)
- Fallback to truncated content for documents without summaries
- Async backfill existing documents in background

## 期待される成果 (Expected Outcomes)

### Quantitative Metrics

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Tokens per search (10 docs) | 80,000 | 8,000 | 90% reduction |
| Search latency | ~200ms | ~200ms | No degradation |
| Ingest latency | ~500ms | ~800ms | +300ms acceptable |
| Storage overhead | 0 | +5% | Minimal impact |
| Agent relevance judgment | Full text | Summary | Sufficient |

### Qualitative Goals

- ✅ Maintain search quality and relevance ranking
- ✅ Zero downtime deployment (phased rollout)
- ✅ Backward compatible (optional full content parameter)
- ✅ Production-ready error handling
- ✅ Graceful migration path for existing documents

## 実装アプローチ (Implementation Approach)

### Phase 1: Schema Migration (5 minutes)
**Goal:** Add brief_summary column without disrupting existing system

```sql
-- Migration: 005_add_brief_summary.sql
ALTER TABLE documents ADD COLUMN brief_summary TEXT NULL;
CREATE INDEX documents_brief_summary_idx ON documents(brief_summary)
WHERE brief_summary IS NOT NULL;
```

**Risk Mitigation:**
- Nullable column = no data migration required
- Partial index = efficient for documents with summaries
- Can rollback easily if needed

### Phase 2: Summary Service (2-3 hours)
**Goal:** Create summarization service and integrate with ingest

**Components:**
1. `aurora_mcp/services/summarizer.py` - LLM-based summarization
2. Update `aurora_ingest()` to generate summaries
3. Add caching (1-hour TTL) to reduce API costs
4. Graceful error handling (store NULL on failure)

**Design Pattern:**
- Similar to `QueryExpander` service (proven pattern)
- Reuse existing LLM configuration
- Extractive summarization (2-3 sentences, 100-200 tokens)

### Phase 3: Search Logic Updates (1-2 hours)
**Goal:** Modify search to return summaries by default

**Changes:**
1. Update `aurora_search()` to return `brief_summary` instead of `content`
2. Add `include_full_content` parameter (default: `false`)
3. Fallback logic: if `brief_summary IS NULL`, return truncated content
4. Update MCP tool documentation

**Backward Compatibility:**
- Agents can opt-in to full content with `include_full_content=true`
- Existing behavior available via parameter
- No breaking changes

### Phase 4: Backfill Script (1 hour + async runtime)
**Goal:** Generate summaries for existing documents

**Implementation:**
1. `scripts/backfill_summaries.py` - batch processing script
2. Rate-limited (10 docs/minute to avoid API quota)
3. Progress tracking (resume from last checkpoint)
4. Logging and error reporting

**Execution Strategy:**
- Run in background (non-blocking)
- Process oldest documents first
- Can run over hours/days without impacting system

## リスクと対策 (Risks & Mitigation)

### Risk 1: Summary Quality
**Risk:** LLM-generated summaries may lose important context
**Mitigation:**
- Agents can always fetch full content via `aurora_retrieve()`
- Test summary quality with sample documents
- Adjust prompt if quality is insufficient

### Risk 2: Ingest Latency Increase
**Risk:** Adding summarization increases ingest time by ~300ms
**Mitigation:**
- Acceptable tradeoff (one-time cost, many-time benefit)
- Async summarization option for future optimization
- Cache prevents re-summarization of duplicate content

### Risk 3: API Quota Exhaustion
**Risk:** Backfill may hit OpenAI API rate limits
**Mitigation:**
- Rate-limited processing (10 docs/minute)
- Exponential backoff on errors
- Resumable from checkpoint

### Risk 4: Migration Complexity
**Risk:** Phased rollout may introduce inconsistent behavior
**Mitigation:**
- Nullable column + fallback logic ensures consistency
- Gradual improvement as backfill progresses
- Clear documentation of expected behavior

## 成功基準 (Success Criteria)

### Must Have (P0)
- [ ] Schema migration completes without errors
- [ ] New documents get summaries automatically
- [ ] Search returns summaries by default
- [ ] Token consumption reduced by >80%
- [ ] No search quality degradation

### Should Have (P1)
- [ ] Backfill script processes existing documents
- [ ] Summary quality validated with sample set
- [ ] Documentation updated (README, MCP tools)
- [ ] Tests added for new functionality

### Nice to Have (P2)
- [ ] Performance metrics dashboard
- [ ] Summary quality monitoring
- [ ] A/B testing framework for summary prompts

## 実装タイムライン (Implementation Timeline)

**Total Estimated Time:** 4-6 hours development + async backfill

```
Phase 1: Schema Migration          [5 min]
Phase 2: Summary Service            [2-3 hours]
Phase 3: Search Logic Updates       [1-2 hours]
Phase 4: Backfill Script            [1 hour]
Testing & Validation                [30 min]
Documentation                       [30 min]
```

## 参考資料 (References)

- Current Aurora architecture analysis (completed 2025-12-22)
- Existing `QueryExpander` service pattern
- Industry best practices: Elasticsearch, Pinecone two-stage retrieval
- OpenAI API documentation for summarization

## 次のステップ (Next Steps)

1. Create PDCA do.md for implementation log
2. Begin Phase 1: Schema migration
3. Continuous documentation in do.md
4. Evaluate results in check.md after completion

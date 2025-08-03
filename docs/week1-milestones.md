# Week 1 Milestones - SmarterVote Corpus-First Implementation

| Day | Milestone | Status | Deliverable |
|-----|-----------|---------|-------------|
| **Day 1** | Infrastructure Foundation | ✅ | Terraform skeleton deployed, empty Cloud Run Job succeeds |
| **Day 2** | DISCOVER + FETCH Implementation | 🔄 | Raw HTML/PDF written to `/raw/mo-senate-2024/` |
| **Day 3** | EXTRACT Pipeline | ⏳ | Plain-text files in `/norm/mo-senate-2024/` |
| **Day 4** | ChromaDB Corpus | ⏳ | Vector database indexed, GPT-4o summary working |
| **Day 5** | LLM Triangulation | ⏳ | Claude 3.5 + Grok-4 added, confidence arbitration |
| **Day 6** | RaceJSON Output | ⏳ | Valid `mo-senate-2024.json` produced |
| **Day 7** | Public Deployment | ⏳ | **smarter.vote/mo-senate-2024** live, feedback gathered |

## Day 1 ✅ - Infrastructure Foundation

### Completed
- [x] Terraform infrastructure skeleton (`infra/`)
- [x] Google Cloud Storage bucket `gs://sv-data` with folder structure:
  - `/raw/` - Downloaded bytes from sources
  - `/norm/` - Extracted plain-text content  
  - `/out/` - Final RaceJSON outputs
  - `/arb/` - Arbitration logs and minority views
- [x] Cloud Run Job `race-worker` for pipeline execution
- [x] Pub/Sub topic `race-jobs` for async processing
- [x] Secret Manager for API keys (OpenAI, Anthropic, Grok, Google Search)
- [x] Service accounts with proper IAM permissions
- [x] CI/CD pipeline for automated deployment

### Infrastructure Components
```bash
# Core Resources Created
├── Cloud Storage: gs://{project-id}-sv-data/
├── Cloud Run Job: race-worker  
├── Pub/Sub Topic: race-jobs
├── Secret Manager: openai-api-key, anthropic-api-key, grok-api-key
├── Service Accounts: race-worker, enqueue-api, pubsub-invoker
└── IAM Bindings: storage.objectAdmin, secretmanager.secretAccessor
```

### Test Verification
```bash
# Verify infrastructure deployment
gcloud run jobs describe race-worker --region=us-central1
gcloud storage ls gs://{project-id}-sv-data/
gcloud pubsub topics list --filter="name:race-jobs"
```

## Day 2 🔄 - DISCOVER + FETCH for MO Senate

### Target Deliverable
Write raw HTML/PDF for **Missouri Senate 2024** race to `/raw/mo-senate-2024/`

### Implementation Plan
1. **Seed URL Discovery**
   - Ballotpedia: Missouri Senate 2024 race page
   - FEC: Josh Hawley and challenger candidate profiles  
   - ProPublica: Congressional data
   - OpenSecrets: Campaign finance data

2. **Google Dork Searches**
   - `"Josh Hawley" site:gov`
   - `"Josh Hawley" site:org`  
   - `"Josh Hawley" "Missouri Senate" 2024`

3. **Content Fetching**
   - HTTP downloads with proper headers
   - PDF file downloads
   - Rate limiting and retry logic
   - Store in `gs://sv-data/raw/mo-senate-2024/`

### Success Criteria
- [ ] 20+ sources discovered and fetched
- [ ] Raw files stored in GCS with proper metadata
- [ ] Pipeline logs show successful DISCOVER and FETCH steps
- [ ] Manual verification of downloaded content quality

## Technical Implementation Notes

### Pipeline Architecture
```python
# 8-Step Corpus-First Workflow
▶ 1. DISCOVER    # Seed URLs + Google dorks  
▶ 2. FETCH       # Download → /raw/{race}/
▶ 3. EXTRACT     # HTML/PDF → /norm/{race}/
▶ 4. BUILD CORPUS # ChromaDB indexing
▶ 5. FRESH ISSUE SEARCH # Google Custom Search (11 issues)
▶ 6. RAG + 3-MODEL SUMMARY # GPT-4o + Claude 3.5 + Grok-4
▶ 7. ARBITRATE   # 2-of-3 consensus
▶ 8. PUBLISH     # RaceJSON v0.2 → /out/{race}.json
```

### RaceJSON v0.2 Schema
```jsonc
{
  "id": "mo-senate-2024",
  "election_date": "2024-11-05",
  "candidates": [
    {
      "name": "Josh Hawley",
      "party": "Republican", 
      "summary": "...",
      "issues": {
        "Healthcare": {
          "stance": "...",
          "confidence": "high",
          "sources": ["src:bp:hawley_profile"]
        }
        // ... 11 canonical issues
      },
      "top_donors": [...]
    }
  ],
  "updated_utc": "2025-08-03T04:12Z",
  "generator": ["gpt-4o", "claude-3.5", "grok-4"]
}
```

### Canonical Issues (11)
1. Healthcare
2. Economy  
3. Climate/Energy
4. Reproductive Rights
5. Immigration
6. Guns & Safety
7. Foreign Policy
8. LGBTQ+ Rights
9. Education
10. Tech & AI
11. Election Reform

## Command Line Usage

```bash
# Run pipeline locally for development
python scripts/run_local.py mo-senate-2024

# Trigger via API
curl -X POST https://enqueue-api-uc.a.run.app/process \
  -H "Content-Type: application/json" \
  -d '{"race_id": "mo-senate-2024"}'

# Deploy infrastructure  
cd infra/envs/dev
terraform plan -var-file=secrets.tfvars
terraform apply -var-file=secrets.tfvars
```

## Success Metrics

### Week 1 Goals
- [ ] **Technical**: All 8 pipeline steps working end-to-end
- [ ] **Content**: High-quality MO Senate race summary generated
- [ ] **Deployment**: Public site live at smarter.vote/mo-senate-2024
- [ ] **Quality**: 2-of-3 LLM consensus achieved with confidence scoring
- [ ] **Performance**: Full race processing under 10 minutes
- [ ] **Cost**: Staying within GCP free tier limits

### Feedback Collection
- [ ] Share with 5 beta testers for initial feedback
- [ ] Measure page load times and user engagement
- [ ] Validate source diversity and quality
- [ ] Test mobile responsiveness

---

**Next Week**: Scale to 10 additional federal races, optimize performance, add more sophisticated arbitration logic.

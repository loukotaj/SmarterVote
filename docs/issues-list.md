# SmarterVote Issues List
*Current development priorities and blockers for full operational status*

## 🚨 Critical Issues (Blocking Operations)

### Pipeline Core Components - Implementation Status

#### 1. **Vector Database Manager (Corpus Service)** 🟡 MOSTLY IMPLEMENTED
- **Status**: 🟡 Core functionality complete but has remaining TODOs
- **File**: `pipeline/app/step02_corpus/vector_database_manager.py`
- **Completed Features**:
  - ✅ ChromaDB client initialization and configuration
  - ✅ Document chunking strategies with sentence boundary preservation
  - ✅ Vector embedding and search functionality (all-MiniLM-L6-v2)
  - ✅ Persistence layer configured with SQLite storage
  - ✅ Metadata filtering for race-specific and issue-specific searches
  - ✅ Duplicate detection based on content similarity
  - ✅ Content statistics and analytics
  - ✅ Database cleanup and maintenance operations
- **Remaining**: 1 TODO item found in implementation
- **Priority**: P1 - Core functionality works, polish needed
- **Tests**: ✅ Comprehensive test suite at `pipeline/app/step02_corpus/test_service.py`

#### 2. **LLM Summarization Engine** 🟡 PARTIALLY IMPLEMENTED
- **Status**: 🟡 Core logic in place but multiple TODOs remain
- **File**: `pipeline/app/step03_summarise/llm_summarization_engine.py`
- **Remaining**: 4 TODO items identified:
  - Refine prompt templates and response parsing
  - Implement smarter chunking for long content
  - Add actual API calls (currently stubbed)
  - Complete bias detection and moderation checks
- **Priority**: P0 - Essential for multi-LLM consensus
- **Tests**: ✅ `pipeline/app/step03_summarise/test_service.py`

#### 3. **Consensus Arbitration Engine** ✅ IMPLEMENTED
- **Status**: ✅ AI-driven arbitration implementation complete
- **File**: `pipeline/app/step03_summarise/consensus_arbitration_engine.py`
- **Features**: Complete 2-of-3 consensus with AI-driven bias detection
- **Priority**: ✅ P0 - COMPLETED
- **Tests**: ✅ `pipeline/app/step03_summarise/test_arbitration_service.py`

#### 4. **Race Publishing Engine** 🟡 MOSTLY IMPLEMENTED
- **Status**: 🟡 Core publishing works but 11 TODO items remain
- **File**: `pipeline/app/step04_publish/race_publishing_engine.py`
- **Completed Features**:
  - ✅ Cloud Storage upload implemented (Google Cloud Storage)
  - ✅ RaceJSON validation logic with comprehensive business rules
  - ✅ Publication target integrations (local, cloud, database, webhooks, Pub/Sub)
  - ✅ Basic publishing functionality working (evidence: race files in data/published/)
- **Remaining**: 11 TODO items for advanced features:
  - Comprehensive data transformation pipeline
  - Parallel publication to multiple targets
  - Advanced local file publishing
  - API endpoint integration
  - Enhanced metadata generation
- **Priority**: P1 - Core works, advanced features needed
- **Tests**: ✅ Comprehensive test suite at `pipeline/app/step04_publish/test_service.py`

### Infrastructure & Configuration Issues

#### 5. **Environment Configuration & Dependencies** 🔴 CRITICAL BLOCKER
- **Status**: 🔴 Dependency version conflicts blocking installation
- **Critical Issue**: `torch==2.1.2` not available for Python 3.12 (available: 2.2.0+)
- **Impact**: Prevents successful `pip install -r pipeline/requirements.txt`
- **Files**: `pipeline/requirements.txt`
- **Remaining**:
  - 📋 Update torch version to compatible release (2.2.0+)
  - 📋 Test compatibility with sentence-transformers and chromadb
  - 📋 Local `.env` file setup (user-specific)
  - 📋 Production environment variable documentation
- **Priority**: P0 - BLOCKS DEVELOPMENT AND TESTING

#### 6. **ChromaDB Persistence** ✅ COMPLETED
- **Status**: ✅ Persistent storage configured and validated
- **Features**:
  - ChromaDB uses `CHROMA_PERSIST_DIR` for on-disk storage
  - Data retained across container restarts
  - Backup/restore procedures documented
- **Priority**: P1 - COMPLETED

## 🟡 High Priority Issues (Feature Gaps)

### Testing Coverage Gaps

#### 7. **Test Suite Coverage**
- **Status**: 🟡 Pipeline modules well-tested; coverage expansion needed
- **Current Tests**:
   - `pipeline/app/step03_summarise/test_service.py`
   - `pipeline/app/step03_summarise/test_arbitration_service.py`
   - `pipeline/app/step04_publish/test_service.py`
   - `pipeline/app/step02_corpus/test_service.py` + `test_basic.py`
  - Total: 9 test files in pipeline
- **Remaining Gaps**:
  - Broader integration tests
  - Additional edge case coverage
  - Full end-to-end pipeline testing
- **Priority**: P1 - Good foundation, needs expansion

#### 8. **Web Frontend Testing** 🔴 CRITICAL GAP
- **Status**: 🔴 Severe testing coverage deficit
- **Critical Issues**:
  - Only 3 test files vs 14 total Svelte components (21% coverage)
  - Only 3 test files vs 9 components in `/lib/components/` (33% coverage)
  - No integration tests for user workflows
  - No Playwright tests configured
  - Missing accessibility testing
- **Tested Components**: CandidateCard, Card, api module
- **Untested**: 11+ components including critical UI elements
- **Priority**: P0 - BLOCKS PRODUCTION READINESS

### API & Service Issues

#### 9. **Service Integration**
- **Status**: 🟡 Services exist but incomplete
- **Issues**:
  - Enqueue API metrics collection stubbed (returns zeros)
  - Race API error handling incomplete
  - No service health checks implemented
  - Missing API rate limiting
- **Priority**: P1 - Production readiness

#### 10. **Data Processing Pipeline Status**
- **Status**: 🟡 Evidence of partial functionality but quality issues
- **Evidence**: 6 race files published in `/data/published/`
  - `mo-senate-2024.json` shows "Data Processing Error" for candidates
  - Some files contain actual race data, others are empty/minimal
- **Issues**:
  - Web frontend uses sample data fallback
  - End-to-end pipeline produces error states
  - Inconsistent data quality across published races
  - No real-time processing from UI
- **Priority**: P0 - Core functionality partially working but unreliable

### Data & Content Issues

#### 11. **Content Fetching Limitations**
- **Status**: 🟡 Basic implementation with TODOs
- **File**: `pipeline/app/fetch/web_content_fetcher.py`
- **Issues**:
  - PDF processing not implemented
  - Social media content fetching missing
  - Rate limiting not configured
  - Dynamic content handling incomplete
- **Priority**: P1 - Impacts data quality

#### 12. **Search Integration**
- **Status**: 🟡 Discovery engine needs Google Search API
- **Issues**:
  - Fresh content search not implemented
  - No content deduplication logic
  - Missing source quality scoring
- **Priority**: P1 - Content discovery limitation

## 🟢 Medium Priority Issues (Enhancements)

### Code Quality & Maintenance

#### 13. **TODO Item Resolution** 🟡 ACTIVE MAINTENANCE NEEDED
- **Status**: 🟡 Multiple TODO items throughout codebase require attention
- **Found in**:
   - `pipeline/app/step04_publish/race_publishing_engine.py` (11 TODOs)
   - `pipeline/app/step03_summarise/llm_summarization_engine.py` (4 TODOs)
   - `pipeline/app/step02_corpus/vector_database_manager.py` (1 TODO)
  - `services/enqueue-api/main.py` (TODO items)
  - Additional files across discovery, fetch, extract modules
- **Impact**: Indicates incomplete implementations and tech debt
- **Priority**: P2 - Maintenance and polish

### Monitoring & Observability

#### 14. **Application Monitoring**
- **Status**: 🟢 Basic Cloud Logging only
- **Missing**:
  - Custom dashboards and metrics
  - Performance monitoring
  - Error tracking and alerting
  - Business metrics collection
- **Priority**: P2 - Operations improvement

#### 15. **CI/CD Pipeline Gaps**
- **Status**: 🟢 Basic workflows exist
- **Missing**:
  - Terraform plan validation in CI
  - Infrastructure drift detection
  - Security scanning
  - Performance benchmarking
- **Priority**: P2 - Development workflow

### Security & Compliance

#### 16. **Security Hardening**
- **Status**: 🟢 Basic IAM configured
- **Missing**:
  - API key rotation strategy
  - Network security policies
  - Input sanitization review
  - Audit logging
- **Priority**: P2 - Security posture

### Performance & Scalability

#### 17. **Multi-Region Support**
- **Status**: 🟢 Single region deployment
- **Missing**:
  - Cross-region replication
  - CDN integration
  - Global load balancing
- **Priority**: P3 - Scale planning

#### 18. **Database Optimization**
- **Status**: 🟢 Basic storage configured
- **Missing**:
  - Index optimization
  - Query performance monitoring
  - Backup automation
- **Priority**: P3 - Performance optimization

## 📋 Action Plan for Operational Status

### Phase 1: Critical Blockers (Week 1) - ⚠️ PRIORITY
1. 🔴 **Fix dependency conflicts** - Update torch version in requirements.txt
2. 🔴 **Resolve web testing gap** - Add tests for 11+ untested components  
3. 🟡 **Complete LLM engine** - Address 4 TODO items, especially API integration
4. 🟡 **Fix data processing errors** - Debug candidate processing failures

### Phase 2: Core Pipeline Completion (Weeks 2-3) - 🟡 60% COMPLETED
1. ✅ Implement ChromaDB client and basic vector operations (DONE)
2. 🟡 Complete LLM API integrations (partially done, TODOs remain)
3. ✅ Create basic consensus arbitration logic (DONE)
4. ✅ Set up environment configuration system (DONE)
5. ✅ Add critical test coverage for vector database (DONE)
6. 🟡 Complete Race Publishing Engine (core works, 11 TODOs remain)

### Phase 3: Data Processing & Quality (Weeks 4-5)
1. Complete content fetching implementations
2. Fix data processing pipeline errors
3. Add Google Search API integration
4. Create comprehensive test suites
5. Set up proper error handling

### Phase 4: Production Readiness (Weeks 6-7)
1. Add monitoring and alerting
2. Complete security hardening
3. Implement CI/CD improvements
4. Add performance optimization
5. Documentation completion

### Phase 5: Scale & Enhancement (Ongoing)
1. Multi-region deployment
2. Advanced features (bias detection, fact-checking)
3. UI/UX improvements
4. Analytics and reporting

## 🎯 Success Metrics

- 🟡 **Pipeline Completeness**: 4/7 core engines functional, 3 need TODO resolution
- 🔴 **Test Coverage**: Good pipeline coverage, critical web frontend gap (21% coverage)
- 🟡 **End-to-End**: Partial success - races published but with data errors
- ⚠️ **Performance**: Cannot assess due to dependency installation issues
- 🟡 **Reliability**: Core infrastructure works, data quality inconsistent
- 🟡 **Quality**: Consensus arbitration complete, but data processing unreliable

---

*Last updated: December 20, 2024*
*Total Issues: 18 (1 Critical Blocker, 2 Critical Gaps, 8 High Priority, 7 Medium Priority)*
*Status: Pipeline 60% functional, critical dependency and testing blockers identified*

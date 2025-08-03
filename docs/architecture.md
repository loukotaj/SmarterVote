# SmarterVote Architecture

## Overview

SmarterVote is a comprehensive electoral analysis platform that processes and summarizes candidate information using AI-powered data processing pipelines.

## System Architecture

### Components

#### 1. Data Pipeline (`pipeline/`)
- **Discover**: URL discovery and search API integration
- **Fetch**: HTTP download and data collection
- **Extract**: Content extraction from HTML, PDF, and JSON sources
- **Corpus**: ChromaDB vector database for content indexing
- **Summarize**: AI model integration (GPT-4o, Claude-3.5, Grok-4)
- **Arbitrate**: Confidence scoring and validation logic
- **Publish**: Final data output in structured JSON format

#### 2. Services (`services/`)
- **Enqueue API**: REST API for triggering data processing via Pub/Sub

#### 3. Web Frontend (`web/`)
- **SvelteKit**: Modern web framework for the user interface
- **Dynamic routing**: Race-specific pages with slug-based routing

#### 4. Infrastructure (`infra/`)
- **Terraform**: Infrastructure as Code for cloud resources
- **Modular design**: Reusable modules for common resources

## Data Flow

1. **Input**: Electoral race information and candidate data sources
2. **Discovery**: Automated URL discovery and content identification
3. **Extraction**: Content processing and text extraction
4. **Analysis**: AI-powered summarization and fact-checking
5. **Storage**: Vector database storage for similarity search
6. **Output**: Structured race data with candidate summaries
7. **Presentation**: Web interface for public consumption

## Technology Stack

- **Backend**: Python with Pydantic for data validation
- **Frontend**: SvelteKit with TypeScript
- **Database**: ChromaDB for vector storage
- **AI**: Multiple LLM providers for redundancy and accuracy
- **Infrastructure**: Google Cloud Platform with Terraform
- **CI/CD**: GitHub Actions
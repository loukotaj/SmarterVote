# SmarterVote

A comprehensive platform for analyzing and summarizing electoral race information using AI-powered data pipeline.

## Project Overview

SmarterVote aggregates, processes, and analyzes electoral race data from multiple sources to provide voters with comprehensive, unbiased summaries of candidates and their positions.

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+
- Docker
- Terraform

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/loukotaj/SmarterVote.git
   cd SmarterVote
   ```

2. **Set up Python environment**
   ```bash
   cd pipeline
   pip install -r requirements.txt
   ```

3. **Set up web frontend**
   ```bash
   cd web
   npm install
   npm run dev
   ```

4. **Run local pipeline**
   ```bash
   python scripts/run_local.py
   ```

## Architecture

- **Pipeline**: Python-based ETL system for data processing
- **Services**: Cloud Run microservices for API endpoints
- **Web**: SvelteKit frontend for user interface
- **Infrastructure**: Terraform for cloud resource management

## Documentation

See the `docs/` directory for detailed architecture documentation and issue tracking.

## Contributing

Please read our contributing guidelines and code of conduct before submitting pull requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

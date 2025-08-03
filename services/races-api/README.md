# Races API

This service serves published race data as a simple FastAPI application.

## Running Locally

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Ensure sample data is available**
   A dummy race file is provided at `../../data/published/mo-senate-2024.json`. The
   service reads JSON files from the directory specified by the `DATA_DIR`
   environment variable (defaults to `data/published` relative to the project
   root).

3. **Start the API**
   From the repository root run:
   ```bash
   python services/races-api/main.py
   ```
   The API will listen on `http://localhost:8080`.

4. **Example requests**
   ```bash
   curl http://localhost:8080/races         # list available race IDs
   curl http://localhost:8080/races/mo-senate-2024  # fetch dummy race data
   ```

The web frontend expects the API at `http://localhost:8080` by default, so
running both `npm run dev` inside `web/` and the command above will allow the
UI to display the sample race data locally.

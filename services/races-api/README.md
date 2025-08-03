# Races API

The Races API provides endpoints to serve processed RaceJSON data for the SmarterVote frontend. It reads race data from JSON files in the `data/published/` directory.

## Quick Start

### Prerequisites
- Python 3.10+
- Race data files in `data/published/` directory (see [Adding Demo Data](#adding-demo-data))

### Running Locally

1. **Navigate to the races-api directory:**
   ```powershell
   cd services\races-api
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Run the API server:**
   ```powershell
   python main.py
   ```

The API will start on `http://localhost:8001` by default.

### API Endpoints

- **GET `/races`** - List all available races
  ```
  GET http://localhost:8001/races
  ```

- **GET `/races/{race_id}`** - Get specific race data
  ```
  GET http://localhost:8001/races/tx-governor-2024
  ```

### Example Response

```json
{
  "id": "tx-governor-2024",
  "title": "Texas Governor Race 2024 (Demo Data)",
  "office": "Governor",
  "jurisdiction": "Texas",
  "election_date": "2024-11-05T00:00:00Z",
  "candidates": [
    {
      "name": "Jane Smith",
      "party": "Republican",
      "incumbent": true,
      "issues": {
        "Economy": {
          "stance": "Supports moderate economic policies...",
          "confidence": "high"
        }
      }
    }
  ]
}
```

## Adding Demo Data

The API automatically discovers race files in the `data/published/` directory. Each file should:

1. Be named `{race-id}.json` (e.g., `tx-governor-2024.json`)
2. Contain valid RaceJSON data following the schema in `pipeline/app/schema.py`

### Available Demo Races

The following demo races are included for testing:

- **tx-governor-2024** - Texas Governor race with 3 fictional candidates
- **ca-senate-2024** - California Senate race with 2 fictional candidates  
- **ny-house-03-2024** - New York House District 3 race with 2 fictional candidates

### Creating New Demo Data

To add a new race, create a JSON file in `data/published/` following this structure:

```json
{
  "id": "your-race-id",
  "election_date": "2024-11-05T00:00:00Z",
  "title": "Your Race Title (Demo Data)",
  "office": "Governor|U.S. Senate|U.S. House of Representatives",
  "jurisdiction": "State or District",
  "updated_utc": "2024-03-15T19:15:00Z",
  "generator": ["gpt-4o", "claude-3.5", "grok-4"],
  "candidates": [
    {
      "name": "Candidate Name",
      "party": "Democratic|Republican|Independent",
      "incumbent": true|false,
      "website": "https://example.com/candidate",
      "summary": "Brief candidate description",
      "issues": {
        "Economy": {
          "issue": "Economy",
          "stance": "Candidate's position on this issue",
          "confidence": "high|medium|low",
          "sources": ["src:demo:example"]
        }
      },
      "top_donors": [
        {
          "name": "Donor Name",
          "amount": 50000.0,
          "organization": "Organization Type",
          "source": "src:demo-records:donations-2024"
        }
      ]
    }
  ]
}
```

## Development

### Running Tests

```powershell
python -m pytest test_races_api.py -v
```

### Environment Variables

- `PORT` - Server port (default: 8001)
- `DATA_PATH` - Path to published race data (default: ../../data/published)

### CORS Configuration

The API includes CORS middleware to allow frontend access from different origins during development.

## Using with Frontend

Once the races API is running, you can configure your frontend to use it:

1. **Start the races API** (as described above)
2. **Update frontend configuration** to point to `http://localhost:8001`
3. **Start your frontend development server**

The frontend should now be able to fetch race data from your local API.

## Troubleshooting

### "No races found" Error

- Ensure race JSON files are in the correct `data/published/` directory
- Check that JSON files are valid and follow the RaceJSON schema
- Verify file names match the race IDs inside the files

### Import Errors

- Make sure you're running from the `services/races-api` directory
- Install requirements: `pip install -r requirements.txt`
- Check that the `data/published` path exists relative to the API directory

### Port Already in Use

- Change the port by setting the `PORT` environment variable:
  ```powershell
  $env:PORT = "8002"; python main.py
  ```

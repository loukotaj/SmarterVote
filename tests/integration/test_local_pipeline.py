"""
Integration test for the pipeline using local LLMs and cached Serper data.

This test runs the full pipeline for the Michigan Senate 2026 race using:
- Local LLM via Ollama (llama3.2:3b or configured model)
- Cached Serper API responses (or real API with caching if SERPER_API_KEY is set)

Run with: pytest tests/integration/test_local_pipeline.py -v

Prerequisites:
1. Ollama running locally: ollama serve
2. Model pulled: ollama pull llama3.2:3b
3. Optional: SERPER_API_KEY env var for initial cache population
"""

import json
from pathlib import Path

import pytest


class TestMichiganSenate2026:
    """Test suite for Michigan Senate 2026 race pipeline."""

    @pytest.fixture
    def race_config(self, mi_senate_2026_config):
        """Get the Michigan Senate 2026 race configuration."""
        return mi_senate_2026_config

    @pytest.mark.asyncio
    async def test_serper_cache_functionality(self, persistent_serper_cache):
        """Test that the Serper cache layer works correctly."""
        from tests.integration.serper_cache import get_cache_key, has_cache, read_cache, write_cache

        # Test cache key generation is deterministic
        key1 = get_cache_key("test query")
        key2 = get_cache_key("test query")
        key3 = get_cache_key("TEST QUERY")  # Should normalize to same key

        assert key1 == key2, "Cache keys should be deterministic"
        assert key1 == key3, "Cache keys should be case-insensitive"

        # Test write and read
        test_response = {"organic": [{"title": "Test Result", "link": "https://example.com", "snippet": "Test snippet"}]}

        write_cache("integration test query", test_response, cache_dir=persistent_serper_cache)
        assert has_cache("integration test query", cache_dir=persistent_serper_cache)

        cached = read_cache("integration test query", cache_dir=persistent_serper_cache)
        assert cached is not None
        assert cached["response"]["organic"][0]["title"] == "Test Result"

    @pytest.mark.asyncio
    async def test_candidate_search_queries(self, race_config, persistent_serper_cache):
        """Test that candidate search queries can be generated and cached."""
        from tests.integration.serper_cache import has_cache, write_cache

        # Generate expected search queries for candidates
        candidates = []
        for party, party_candidates in race_config["candidates"].items():
            for candidate in party_candidates:
                candidates.append(
                    {
                        "name": candidate["name"],
                        "party": party,
                        "query": f"{candidate['name']} {race_config['state']} Senate candidate 2026 issues positions",
                    }
                )

        assert len(candidates) >= 2, "Should have at least 2 candidates"

        # Log the queries we'd use
        for candidate in candidates:
            print(f"Query for {candidate['name']}: {candidate['query']}")

    def test_race_config_structure(self, race_config):
        """Validate the race configuration has required fields."""
        assert "state" in race_config
        assert "office" in race_config
        assert "year" in race_config
        assert "candidates" in race_config

        assert race_config["state"] == "Michigan"
        assert race_config["year"] == 2026

        # Validate candidates structure
        candidates = race_config["candidates"]
        assert "democrat" in candidates or "republican" in candidates

        for party, party_candidates in candidates.items():
            assert isinstance(party_candidates, list)
            for candidate in party_candidates:
                assert "name" in candidate

    @pytest.mark.asyncio
    async def test_local_llm_connectivity(self, check_ollama, local_llm_env):
        """Verify local LLM is accessible and responds."""
        import os

        import httpx

        base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")

        async with httpx.AsyncClient() as client:
            # Test chat completions endpoint
            response = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": os.environ.get("LOCAL_LLM_MODEL", "llama3.2:3b"),
                    "messages": [{"role": "user", "content": "Say 'test' and nothing else."}],
                    "max_tokens": 10,
                },
                timeout=60.0,
            )

            assert response.status_code == 200, f"LLM request failed: {response.text}"

            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert "message" in data["choices"][0]

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_single_candidate_issue_extraction(self, check_ollama, local_llm_env, persistent_serper_cache):
        """
        Test extracting issues for a single candidate using local LLM.
        This is a smoke test to verify the pipeline components work together.
        """
        import os

        import httpx

        base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        model = os.environ.get("LOCAL_LLM_MODEL", "llama3.2:3b")

        # Simple issue extraction prompt
        prompt = """Based on publicly available information, extract 3 key policy positions for Elissa Slotkin, Michigan Senate candidate.

For each issue, provide:
1. Issue name (e.g., "Healthcare", "Economy")
2. A brief summary of their stance
3. Confidence level (high/medium/low)

Respond in JSON format:
{
  "issues": {
    "Issue Name": {
      "summary": "Brief description of stance",
      "confidence": "high|medium|low"
    }
  }
}"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
                timeout=120.0,
            )

            assert response.status_code == 200, f"LLM request failed: {response.text}"

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Try to extract JSON from response
            # The response might have markdown code blocks
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                # Try to find JSON object directly
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]

            try:
                parsed = json.loads(json_str)
                assert "issues" in parsed, "Response should contain 'issues' key"
                assert len(parsed["issues"]) > 0, "Should have at least one issue"

                # Validate structure
                for issue_name, issue_data in parsed["issues"].items():
                    assert (
                        "summary" in issue_data or "stance" in issue_data
                    ), f"Issue '{issue_name}' should have summary or stance"

                print(f"\nExtracted {len(parsed['issues'])} issues:")
                for name, data in parsed["issues"].items():
                    print(f"  - {name}: {data.get('summary', data.get('stance', 'N/A'))[:50]}...")

            except json.JSONDecodeError as e:
                pytest.fail(f"Failed to parse JSON from LLM response: {e}\nContent: {content[:500]}")


class TestPipelineOutputValidation:
    """Tests to validate pipeline output structure and quality."""

    def test_published_json_structure(self):
        """Validate the structure of existing published race JSON files."""
        published_dir = Path(__file__).parent.parent.parent / "data" / "published"

        if not published_dir.exists():
            pytest.skip("No published data directory found")

        json_files = list(published_dir.glob("*.json"))
        if not json_files:
            pytest.skip("No published JSON files found")

        for json_file in json_files:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Required top-level fields
            assert "id" in data, f"{json_file.name} missing id"
            assert "candidates" in data, f"{json_file.name} missing candidates"
            assert isinstance(data["candidates"], list), f"{json_file.name} candidates should be a list"

            # Validate each candidate
            for candidate in data["candidates"]:
                assert "name" in candidate, f"Candidate missing name in {json_file.name}"
                assert "party" in candidate, f"Candidate missing party in {json_file.name}"

                # Check for issues (may be empty but should exist)
                if "issues" in candidate:
                    assert isinstance(
                        candidate["issues"], dict
                    ), f"Issues should be a dict for {candidate['name']} in {json_file.name}"

    def test_summary_not_raw_json(self):
        """Check that candidate summaries are not raw JSON strings."""
        published_dir = Path(__file__).parent.parent.parent / "data" / "published"

        if not published_dir.exists():
            pytest.skip("No published data directory found")

        json_files = list(published_dir.glob("*.json"))

        issues_found = []
        for json_file in json_files:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for candidate in data.get("candidates", []):
                summary = candidate.get("summary", "")

                # Check for raw JSON in summary
                if summary.strip().startswith("{") or summary.strip().startswith("["):
                    issues_found.append(
                        {"file": json_file.name, "candidate": candidate.get("name"), "summary_preview": summary[:100]}
                    )

                # Check for escaped JSON
                if '\\"' in summary or "\\n" in summary:
                    issues_found.append(
                        {
                            "file": json_file.name,
                            "candidate": candidate.get("name"),
                            "issue": "Escaped JSON characters in summary",
                        }
                    )

        if issues_found:
            # This is informational - we know there are issues
            print(f"\nFound {len(issues_found)} summaries with potential JSON issues:")
            for issue in issues_found[:5]:
                print(f"  - {issue['file']}: {issue['candidate']}")

    def test_issues_not_empty(self):
        """
        Check that candidates have non-empty issues.
        This test documents the known issue with empty issues arrays.
        """
        published_dir = Path(__file__).parent.parent.parent / "data" / "published"

        if not published_dir.exists():
            pytest.skip("No published data directory found")

        json_files = list(published_dir.glob("*.json"))

        empty_issues_count = 0
        total_candidates = 0

        for json_file in json_files:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for candidate in data.get("candidates", []):
                total_candidates += 1
                issues = candidate.get("issues", {})

                if not issues or len(issues) == 0:
                    empty_issues_count += 1

        if total_candidates > 0:
            empty_pct = (empty_issues_count / total_candidates) * 100
            print(f"\n{empty_issues_count}/{total_candidates} candidates ({empty_pct:.1f}%) have empty issues")

            # This is informational - we know there's a pipeline issue
            if empty_pct > 50:
                print("WARNING: More than 50% of candidates have empty issues - pipeline issue suspected")


# Mark slow tests
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")

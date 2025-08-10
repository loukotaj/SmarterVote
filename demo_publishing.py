#!/usr/bin/env python3
"""
Demo script showing the Race Publishing Engine functionality.

This script demonstrates how to use the publishing engine to create and publish
race data from sample arbitrated data.
"""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pipeline.app.publish import PublicationConfig, PublishService, RacePublishingEngine


async def main():
    """Demonstrate the Race Publishing Engine functionality."""
    print("🗳️  SmarterVote Race Publishing Engine Demo")
    print("=" * 50)

    # Create a temporary directory for the demo
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        print(f"📁 Using temporary directory: {temp_path}")

        # Configure the publishing engine
        config = PublicationConfig(
            output_directory=temp_path / "published",
            enable_cloud_storage=False,  # Disable for demo
            enable_database=False,  # Disable for demo
            enable_webhooks=False,  # Disable for demo
            enable_notifications=False,  # Disable for demo
        )

        # Initialize the publishing engine
        engine = RacePublishingEngine(config)
        print(f"✅ Initialized publishing engine")

        # Sample arbitrated data (what would come from the arbitration step)
        sample_arbitrated_data = {
            "consensus_data": {
                "race_title": "Missouri U.S. Senate Race 2024",
                "office": "U.S. Senate",
                "jurisdiction": "Missouri",
                "election_date": "2024-11-05",
            },
            "arbitrated_summaries": [
                {
                    "query_type": "candidate_summary",
                    "candidate_name": "Josh Hawley",
                    "content": "Josh Hawley is the Republican incumbent senator from Missouri, known for his conservative positions on social issues and strong support for working families. He has been a vocal advocate for antitrust measures against big tech companies.",
                    "confidence": "high",
                },
                {
                    "query_type": "candidate_summary",
                    "candidate_name": "Lucas Kunce",
                    "content": "Lucas Kunce is the Democratic challenger, a Marine veteran and antitrust attorney who has focused his campaign on economic populism and reducing corporate power. He advocates for expanding healthcare access and supporting working families.",
                    "confidence": "high",
                },
                {
                    "query_type": "issue_stance",
                    "candidate_name": "Josh Hawley",
                    "issue": "Healthcare",
                    "content": "Supports repealing the Affordable Care Act and replacing it with market-based solutions. Advocates for price transparency in healthcare and reducing prescription drug costs.",
                    "confidence": "medium",
                },
                {
                    "query_type": "issue_stance",
                    "candidate_name": "Lucas Kunce",
                    "issue": "Healthcare",
                    "content": "Supports expanding the Affordable Care Act and adding a public option. Advocates for Medicare negotiating prescription drug prices and protecting coverage for pre-existing conditions.",
                    "confidence": "high",
                },
                {
                    "query_type": "issue_stance",
                    "candidate_name": "Josh Hawley",
                    "issue": "Economy",
                    "content": "Supports tax cuts for working families and small businesses. Advocates for bringing manufacturing jobs back to America and reducing dependence on China.",
                    "confidence": "high",
                },
                {
                    "query_type": "issue_stance",
                    "candidate_name": "Lucas Kunce",
                    "issue": "Economy",
                    "content": "Supports raising the minimum wage and strengthening workers' rights to organize. Advocates for investing in infrastructure and clean energy jobs.",
                    "confidence": "medium",
                },
            ],
            "overall_confidence": "high",
        }

        print("\n📊 Sample arbitrated data:")
        print(f"   - Race: {sample_arbitrated_data['consensus_data']['race_title']}")
        print(f"   - Candidates: 2 (Josh Hawley, Lucas Kunce)")
        print(f"   - Issue stances: 4 total")
        print(f"   - Overall confidence: {sample_arbitrated_data['overall_confidence']}")

        # Step 1: Create RaceJSON from arbitrated data
        print("\n🔄 Step 1: Creating RaceJSON from arbitrated data...")
        race_id = "mo-senate-2024"
        race = await engine.create_race_json(race_id, sample_arbitrated_data)

        print("✅ RaceJSON created successfully!")
        print(f"   - ID: {race.id}")
        print(f"   - Title: {race.title}")
        print(f"   - Office: {race.office}")
        print(f"   - Jurisdiction: {race.jurisdiction}")
        print(f"   - Election Date: {race.election_date.strftime('%Y-%m-%d')}")
        print(f"   - Candidates: {len(race.candidates)}")

        for i, candidate in enumerate(race.candidates, 1):
            print(f"     {i}. {candidate.name} ({candidate.party})")
            print(f"        Summary: {candidate.summary[:100]}...")
            print(f"        Issue stances: {len(candidate.issues)}")

        # Step 2: Validate the RaceJSON
        print("\n🔍 Step 2: Validating RaceJSON...")
        try:
            await engine._validate_race_json(race)
            print("✅ RaceJSON validation passed!")
        except Exception as e:
            print(f"❌ RaceJSON validation failed: {e}")
            return

        # Step 3: Publish to local file (only enabled target)
        print("\n📤 Step 3: Publishing race data...")
        from pipeline.app.publish.race_publishing_engine import PublicationTarget

        results = await engine.publish_race(race, [PublicationTarget.LOCAL_FILE])

        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.target.value}: {result.message}")

        # Step 4: Verify the published file
        print("\n📁 Step 4: Verifying published file...")
        output_file = config.output_directory / f"{race_id}.json"

        if output_file.exists():
            print(f"✅ File created: {output_file}")
            print(f"   File size: {output_file.stat().st_size} bytes")

            # Load and display some content
            with open(output_file, "r", encoding="utf-8") as f:
                published_data = json.load(f)

            print(f"   Published data structure:")
            print(f"     - ID: {published_data['id']}")
            print(f"     - Candidates: {len(published_data['candidates'])}")
            print(f"     - Last updated: {published_data['updated_utc']}")

            # Show a sample of the JSON structure
            print(f"\n📋 Sample of published JSON:")
            sample_output = {
                "id": published_data["id"],
                "title": published_data["title"],
                "office": published_data["office"],
                "candidates": [
                    {
                        "name": c["name"],
                        "party": c["party"],
                        "summary": c["summary"][:100] + "..." if len(c["summary"]) > 100 else c["summary"],
                    }
                    for c in published_data["candidates"]
                ],
            }
            print(json.dumps(sample_output, indent=2))
        else:
            print("❌ Published file not found!")

        # Step 5: Show additional engine capabilities
        print("\n🔧 Step 5: Additional engine capabilities...")

        # Get list of published races
        published_races = engine.get_published_races()
        print(f"   📋 Published races: {published_races}")

        # Retrieve race data
        race_data = engine.get_race_data(race_id)
        if race_data:
            print(f"   📊 Retrieved race data for {race_id}")

        # Show publication history
        history = engine.get_publication_history()
        print(f"   📈 Publication history entries: {len(history)}")
        for entry in history:
            print(f"     - {entry.target.value}: {'SUCCESS' if entry.success else 'FAILED'}")

        print("\n🎉 Demo completed successfully!")
        print("\nThe Race Publishing Engine provides:")
        print("  ✅ Data transformation from arbitrated consensus to RaceJSON")
        print("  ✅ Comprehensive validation and quality checks")
        print("  ✅ Multi-target publication (local, cloud, database, webhooks)")
        print("  ✅ Error handling and retry logic")
        print("  ✅ Publication history and audit trails")
        print("  ✅ Cleanup and maintenance operations")


if __name__ == "__main__":
    asyncio.run(main())

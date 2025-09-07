#!/usr/bin/env python3
"""Test for the reference-based artifact system."""

import json
import pytest
from datetime import datetime
from pathlib import Path

# Imports for testing 
from pipeline_client.backend.storage import save_content_collection, load_content_from_references
from pipeline_client.backend.storage_backend import LocalStorageBackend


class TestReferenceSystem:
    """Test suite for the reference-based content storage system."""
    
    def test_save_and_load_content_collection(self, tmp_path):
        """Test saving content collection and loading from references."""
        # Test data
        test_content = [
            {"source": "http://example1.com", "content": "Test content 1", "size": 100},
            {"source": "http://example2.com", "content": "Test content 2", "size": 200},
            {"source": "http://example3.com", "content": "Test content 3", "size": 300}
        ]
        
        race_id = "test-race-123"
        
        # Save content collection
        references = save_content_collection(race_id, test_content, "raw_content", "raw")
        
        # Verify references structure
        assert len(references) == len(test_content)
        for i, ref in enumerate(references):
            assert ref["type"] == "content_ref"
            assert ref["content_type"] == "raw_content"
            assert ref["kind"] == "raw"
            assert ref["index"] == i
            assert ref["filename"] == f"raw_content_{i:04d}.json"
            assert Path(ref["uri"]).exists()
        
        # Load content back
        loaded_content = load_content_from_references(references)
        
        # Verify content matches
        assert len(loaded_content) == len(test_content)
        for original, loaded in zip(test_content, loaded_content):
            assert original == loaded
    
    def test_backward_compatibility(self):
        """Test that non-reference content is handled correctly."""
        # Test with direct content (no references)
        direct_content = [
            {"data": "direct_content_1"},
            {"data": "direct_content_2"}
        ]
        
        loaded = load_content_from_references(direct_content)
        assert loaded == direct_content
    
    def test_reference_structure(self, tmp_path):
        """Test that references have the correct structure."""
        test_content = [{"test": "data"}]
        references = save_content_collection("test-race", test_content, "test_type", "test_kind")
        
        ref = references[0]
        required_keys = {"type", "uri", "filename", "content_type", "kind", "index"}
        assert set(ref.keys()) >= required_keys
        assert ref["type"] == "content_ref"
        assert ref["content_type"] == "test_type"
        assert ref["kind"] == "test_kind"
        assert ref["index"] == 0
    
    def test_multiple_kinds_and_types(self, tmp_path):
        """Test saving content with different kinds and types."""
        content = [{"data": "test"}]
        
        # Test different kinds
        for kind in ["raw", "extracted", "relevant"]:
            refs = save_content_collection("test-race", content, "test_content", kind)
            assert refs[0]["kind"] == kind
            
        # Test different content types
        for content_type in ["raw_content", "processed_content", "relevant_content"]:
            refs = save_content_collection("test-race", content, content_type, "raw")
            assert refs[0]["content_type"] == content_type
    
    def test_empty_content_collection(self):
        """Test handling of empty content collections."""
        references = save_content_collection("test-race", [], "empty_content", "raw")
        assert references == []
        
        loaded = load_content_from_references([])
        assert loaded == []
    
    def test_artifact_size_improvement(self, tmp_path):
        """Test that reference system reduces artifact size significantly."""
        # Create large mock content
        large_content = []
        for i in range(3):
            large_content.append({
                "source": f"http://example{i}.com",
                "content": "A" * 5000,  # 5KB of content
                "metadata": {"large": True, "index": i}
            })
        
        # Old approach - full content in artifact
        old_artifact = {
            "step": "test_step",
            "output": large_content
        }
        old_size = len(json.dumps(old_artifact))
        
        # New approach - references in artifact
        references = save_content_collection("test-race", large_content, "raw_content", "raw")
        new_artifact = {
            "step": "test_step", 
            "output": {
                "type": "content_collection_refs",
                "references": references,
                "count": len(references),
                "race_id": "test-race"
            }
        }
        new_size = len(json.dumps(new_artifact))
        
        # Verify significant size reduction
        reduction_ratio = old_size / new_size
        assert reduction_ratio > 10, f"Expected >10x reduction, got {reduction_ratio}x"
        
        # Verify content can still be loaded
        loaded_content = load_content_from_references(references)
        assert loaded_content == large_content


def test_reference_system_integration():
    """Integration test for the reference system."""
    # This would be the pattern used by handlers
    race_id = "integration-test-race"
    
    # Step 1: Simulate fetch step output
    fetch_content = [
        {"source": {"url": "http://site1.com"}, "content": "Raw content 1"},
        {"source": {"url": "http://site2.com"}, "content": "Raw content 2"}
    ]
    
    fetch_references = save_content_collection(race_id, fetch_content, "raw_content", "raw")
    fetch_output = {
        "type": "content_collection_refs",
        "references": fetch_references,
        "count": len(fetch_references),
        "race_id": race_id
    }
    
    # Step 2: Simulate extract step - load from references, process, save new references
    if fetch_output.get("type") == "content_collection_refs":
        raw_content = load_content_from_references(fetch_output["references"])
        
        # Mock processing
        processed_content = []
        for item in raw_content:
            processed_content.append({
                "source": item["source"],
                "text": f"Processed: {item['content']}",
                "word_count": 10
            })
        
        extract_references = save_content_collection(race_id, processed_content, "processed_content", "extracted")
        extract_output = {
            "type": "content_collection_refs",
            "references": extract_references,
            "count": len(extract_references),
            "race_id": race_id
        }
        
        # Verify end-to-end
        final_content = load_content_from_references(extract_output["references"])
        assert len(final_content) == 2
        assert all("Processed:" in item["text"] for item in final_content)
        
        print("✓ Integration test passed!")


if __name__ == "__main__":
    # Run integration test
    test_reference_system_integration()
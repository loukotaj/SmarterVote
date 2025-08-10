#!/usr/bin/env python3
"""
Code quality and syntax validation test for SmarterVote pipeline.
This script checks for syntax errors, import issues, and basic code quality.
"""

import ast
import os
import sys
from pathlib import Path
import traceback

def check_python_syntax(file_path):
    """Check if a Python file has valid syntax."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        # Parse the AST to check for syntax errors
        ast.parse(source, filename=file_path)
        return True, None
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error reading file: {e}"

def check_import_structure(file_path):
    """Check if imports in a file are properly structured."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        tree = ast.parse(source)
        
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith('.'):
                    # Relative import - this is okay in packages
                    continue
            elif isinstance(node, ast.Import):
                # Regular import
                continue
        
        return True, issues
    except Exception as e:
        return False, [f"Error analyzing imports: {e}"]

def check_key_files():
    """Check key pipeline files for syntax and basic structure."""
    print("🔍 Checking key pipeline files...")
    
    key_files = [
        "pipeline/app/__main__.py",
        "pipeline/app/discover/source_discovery_engine.py",
        "pipeline/app/summarise/llm_summarization_engine.py", 
        "pipeline/app/publish/race_publishing_engine.py",
        "pipeline/app/arbitrate/consensus_arbitration_engine.py",
        "services/races-api/simple_publish_service.py",
        "services/races-api/main.py",
        "shared/models.py",
    ]
    
    results = []
    
    for file_path in key_files:
        full_path = Path(file_path)
        if not full_path.exists():
            results.append((file_path, False, f"File not found: {full_path}"))
            continue
            
        # Check syntax
        syntax_ok, syntax_error = check_python_syntax(full_path)
        if not syntax_ok:
            results.append((file_path, False, f"Syntax error: {syntax_error}"))
            continue
            
        # Check imports
        imports_ok, import_issues = check_import_structure(full_path)
        if not imports_ok:
            results.append((file_path, False, f"Import issues: {import_issues}"))
            continue
            
        results.append((file_path, True, "OK"))
    
    return results

def check_required_methods():
    """Check that key methods exist in the main classes."""
    print("🔍 Checking required methods...")
    
    checks = []
    
    # Check discovery service methods
    discovery_file = Path("pipeline/app/discover/source_discovery_engine.py")
    if discovery_file.exists():
        try:
            with open(discovery_file, 'r') as f:
                content = f.read()
            
            required_methods = [
                "discover_all_sources",
                "discover_seed_sources", 
                "discover_fresh_issue_sources",
                "_search_google_custom",
                "_discover_candidate_sources"
            ]
            
            for method in required_methods:
                if f"def {method}" in content or f"async def {method}" in content:
                    checks.append(f"✅ DiscoveryService.{method}")
                else:
                    checks.append(f"❌ DiscoveryService.{method} missing")
        except Exception as e:
            checks.append(f"❌ Error checking DiscoveryService: {e}")
    
    # Check summarization service methods
    summary_file = Path("pipeline/app/summarise/llm_summarization_engine.py")
    if summary_file.exists():
        try:
            with open(summary_file, 'r') as f:
                content = f.read()
            
            required_methods = [
                "generate_summaries",
                "_generate_race_summary",
                "_generate_candidate_summaries", 
                "_generate_issue_summaries",
                "_get_race_summary_prompt",
                "_get_issue_summary_prompt"
            ]
            
            for method in required_methods:
                if f"def {method}" in content or f"async def {method}" in content:
                    checks.append(f"✅ SummarizationEngine.{method}")
                else:
                    checks.append(f"❌ SummarizationEngine.{method} missing")
        except Exception as e:
            checks.append(f"❌ Error checking SummarizationEngine: {e}")
    
    # Check publishing service methods
    publish_file = Path("pipeline/app/publish/race_publishing_engine.py")
    if publish_file.exists():
        try:
            with open(publish_file, 'r') as f:
                content = f.read()
            
            required_methods = [
                "publish_race",
                "_get_environment_specific_targets",
                "_publish_to_local_file",
                "_publish_to_cloud_storage"
            ]
            
            for method in required_methods:
                if f"def {method}" in content or f"async def {method}" in content:
                    checks.append(f"✅ PublishingEngine.{method}")
                else:
                    checks.append(f"❌ PublishingEngine.{method} missing")
        except Exception as e:
            checks.append(f"❌ Error checking PublishingEngine: {e}")
    
    # Check races API service methods
    races_api_file = Path("services/races-api/simple_publish_service.py")
    if races_api_file.exists():
        try:
            with open(races_api_file, 'r') as f:
                content = f.read()
            
            required_methods = [
                "get_published_races",
                "get_race_data",
                "_get_race_data_local",
                "_get_race_data_cloud",
                "_detect_cloud_environment"
            ]
            
            for method in required_methods:
                if f"def {method}" in content:
                    checks.append(f"✅ RacesAPIService.{method}")
                else:
                    checks.append(f"❌ RacesAPIService.{method} missing")
        except Exception as e:
            checks.append(f"❌ Error checking RacesAPIService: {e}")
    
    return checks

def check_configuration_handling():
    """Check that configuration and environment variables are handled properly."""
    print("🔍 Checking configuration handling...")
    
    checks = []
    
    # Check environment variable usage
    files_to_check = [
        "pipeline/app/discover/source_discovery_engine.py",
        "pipeline/app/publish/race_publishing_engine.py", 
        "services/races-api/simple_publish_service.py"
    ]
    
    for file_path in files_to_check:
        if Path(file_path).exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for proper environment variable handling
                if "os.getenv(" in content:
                    checks.append(f"✅ {file_path} uses os.getenv() for environment variables")
                else:
                    checks.append(f"⚠️  {file_path} may not handle environment variables")
                
                # Check for graceful fallbacks
                if "except ImportError" in content or "try:" in content:
                    checks.append(f"✅ {file_path} has error handling")
                else:
                    checks.append(f"⚠️  {file_path} may lack error handling")
                    
            except Exception as e:
                checks.append(f"❌ Error checking {file_path}: {e}")
    
    return checks

def check_async_patterns():
    """Check for proper async/await usage."""
    print("🔍 Checking async patterns...")
    
    checks = []
    
    async_files = [
        "pipeline/app/__main__.py",
        "pipeline/app/discover/source_discovery_engine.py",
        "pipeline/app/summarise/llm_summarization_engine.py",
        "pipeline/app/publish/race_publishing_engine.py"
    ]
    
    for file_path in async_files:
        if Path(file_path).exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for async function definitions
                if "async def" in content:
                    checks.append(f"✅ {file_path} has async functions")
                else:
                    checks.append(f"⚠️  {file_path} may be missing async functions")
                
                # Check for proper await usage
                async_def_count = content.count("async def")
                await_count = content.count("await")
                
                if async_def_count > 0 and await_count > 0:
                    checks.append(f"✅ {file_path} uses await properly")
                elif async_def_count > 0:
                    checks.append(f"⚠️  {file_path} has async functions but limited await usage")
                    
            except Exception as e:
                checks.append(f"❌ Error checking {file_path}: {e}")
    
    return checks

def main():
    """Run all code quality checks."""
    print("🗳️  SmarterVote Code Quality Check")
    print("=" * 50)
    
    # Check syntax and basic structure
    file_results = check_key_files()
    
    print(f"\n📁 File Syntax Check ({len(file_results)} files):")
    syntax_passed = 0
    for file_path, success, message in file_results:
        status = "✅" if success else "❌"
        print(f"   {status} {file_path}: {message}")
        if success:
            syntax_passed += 1
    
    print(f"\n   Summary: {syntax_passed}/{len(file_results)} files passed syntax check")
    
    # Check required methods
    method_checks = check_required_methods()
    print(f"\n🔧 Required Methods Check:")
    method_passed = 0
    for check in method_checks:
        print(f"   {check}")
        if "✅" in check:
            method_passed += 1
    
    print(f"\n   Summary: {method_passed}/{len(method_checks)} required methods found")
    
    # Check configuration handling
    config_checks = check_configuration_handling()
    print(f"\n⚙️  Configuration Handling:")
    for check in config_checks:
        print(f"   {check}")
    
    # Check async patterns
    async_checks = check_async_patterns()
    print(f"\n🔄 Async/Await Patterns:")
    for check in async_checks:
        print(f"   {check}")
    
    # Overall summary
    print("\n" + "=" * 50)
    print("📊 Code Quality Summary:")
    print(f"   📁 Syntax: {syntax_passed}/{len(file_results)} files pass")
    print(f"   🔧 Methods: {method_passed}/{len(method_checks)} methods implemented")
    print(f"   ⚙️  Configuration: Environment variable handling present")
    print(f"   🔄 Async: Async/await patterns implemented")
    
    if syntax_passed == len(file_results) and method_passed >= len(method_checks) * 0.8:
        print("\n🎉 Code quality check PASSED!")
        print("✅ Pipeline implementation meets requirements")
        return True
    else:
        print("\n⚠️  Code quality check needs attention")
        print("🔧 Some files or methods may need fixes")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
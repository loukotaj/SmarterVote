#!/usr/bin/env python3
"""
Generate a test coverage analysis for SmarterVote without requiring external dependencies.

This script analyzes the test files and the codebase to provide insights into
what functionality is covered by tests that can run without external API calls.
"""

import os
import re
from pathlib import Path


def analyze_test_file(test_file):
    """Analyze a test file to understand what it tests."""
    if not Path(test_file).exists():
        return {}
    
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract function/method names being tested
    test_functions = re.findall(r'def (test_\w+)', content)
    
    # Extract what functionality is being tested (look for comments and strings)
    functionality = []
    
    # Look for test descriptions and docstrings
    docstrings = re.findall(r'"""([^"]+)"""', content)
    functionality.extend(docstrings)
    
    # Look for specific functionality mentions
    if 'environment' in content.lower():
        functionality.append("Environment detection")
    if 'query' in content.lower():
        functionality.append("Query generation")
    if 'publish' in content.lower():
        functionality.append("Publishing functionality")
    if 'api' in content.lower():
        functionality.append("API functionality")
    if 'syntax' in content.lower():
        functionality.append("Code syntax validation")
    if 'import' in content.lower():
        functionality.append("Import structure validation")
    if 'async' in content.lower():
        functionality.append("Async/await patterns")
    if 'search' in content.lower():
        functionality.append("Search functionality")
    if 'candidate' in content.lower():
        functionality.append("Candidate processing")
    if 'race' in content.lower():
        functionality.append("Race data handling")
    
    return {
        'test_functions': test_functions,
        'functionality': list(set(functionality)),
        'line_count': len(content.split('\n')),
        'has_mocking': 'mock' in content.lower() or 'Mock' in content
    }


def analyze_codebase():
    """Analyze the codebase to understand the scope of functionality."""
    code_dirs = ['pipeline/app', 'services', 'shared']
    
    total_files = 0
    total_lines = 0
    modules = {}
    
    for code_dir in code_dirs:
        if not Path(code_dir).exists():
            continue
            
        for py_file in Path(code_dir).rglob('*.py'):
            if py_file.name.startswith('test_') or py_file.name == '__init__.py':
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                total_files += 1
                lines = len(content.split('\n'))
                total_lines += lines
                
                # Analyze module functionality
                module_name = str(py_file.relative_to(Path('.'))).replace('/', '.').replace('.py', '')
                
                # Extract classes and functions
                classes = re.findall(r'class (\w+)', content)
                functions = re.findall(r'def (\w+)', content)
                async_functions = re.findall(r'async def (\w+)', content)
                
                modules[module_name] = {
                    'path': str(py_file),
                    'lines': lines,
                    'classes': classes,
                    'functions': functions,
                    'async_functions': async_functions,
                    'has_api_calls': any(api in content for api in ['openai', 'anthropic', 'requests.get', 'httpx']),
                    'has_external_deps': any(dep in content for dep in ['chromadb', 'selenium', 'PyPDF2'])
                }
            except Exception as e:
                print(f"Warning: Could not analyze {py_file}: {e}")
    
    return {
        'total_files': total_files,
        'total_lines': total_lines,
        'modules': modules
    }


def generate_coverage_report():
    """Generate a comprehensive coverage report."""
    print("🗳️  SmarterVote Test Coverage Analysis")
    print("=" * 60)
    
    # Analyze test files
    test_files = ['test_code_quality.py', 'test_pipeline_logic.py', 'test_integration.py']
    
    print("\n📋 Test File Analysis:")
    print("-" * 40)
    
    total_test_functions = 0
    all_functionality = set()
    
    for test_file in test_files:
        if Path(test_file).exists():
            analysis = analyze_test_file(test_file)
            total_test_functions += len(analysis['test_functions'])
            all_functionality.update(analysis['functionality'])
            
            print(f"\n📄 {test_file}:")
            print(f"   • Test functions: {len(analysis['test_functions'])}")
            print(f"   • Lines of code: {analysis['line_count']}")
            print(f"   • Uses mocking: {'Yes' if analysis['has_mocking'] else 'No'}")
            print(f"   • Coverage areas: {', '.join(analysis['functionality'][:3])}...")
    
    # Analyze codebase
    print(f"\n📊 Codebase Analysis:")
    print("-" * 40)
    
    codebase = analyze_codebase()
    
    print(f"   • Total Python files: {codebase['total_files']}")
    print(f"   • Total lines of code: {codebase['total_lines']:,}")
    print(f"   • Test files: {len(test_files)}")
    print(f"   • Test functions: {total_test_functions}")
    
    # Categorize modules by testability without external dependencies
    testable_modules = []
    api_dependent_modules = []
    external_dependent_modules = []
    
    for module_name, module_info in codebase['modules'].items():
        if module_info['has_external_deps']:
            external_dependent_modules.append(module_name)
        elif module_info['has_api_calls']:
            api_dependent_modules.append(module_name)
        else:
            testable_modules.append(module_name)
    
    print(f"\n🎯 Testability Analysis:")
    print("-" * 40)
    print(f"   • Easily testable modules: {len(testable_modules)}")
    print(f"   • API-dependent modules: {len(api_dependent_modules)}")
    print(f"   • External dependency modules: {len(external_dependent_modules)}")
    
    # Coverage breakdown
    print(f"\n📈 Coverage Breakdown:")
    print("-" * 40)
    
    coverage_areas = [
        ("Code Quality", "Syntax checking, import validation, async patterns"),
        ("Business Logic", "Environment detection, query generation, data categorization"),
        ("Integration", "Publishing modes, API fallbacks, data handling"),
        ("Configuration", "Environment variables, cloud detection"),
        ("Error Handling", "Graceful fallbacks, missing data scenarios")
    ]
    
    for area, description in coverage_areas:
        covered = "✅" if any(keyword in ' '.join(all_functionality).lower() 
                            for keyword in area.lower().split()) else "⚠️"
        print(f"   {covered} {area}: {description}")
    
    # Recommendations
    print(f"\n💡 Test Strategy Summary:")
    print("-" * 40)
    print(f"   • Focus: Core business logic and integration without external APIs")
    print(f"   • Coverage: {len(testable_modules)}/{codebase['total_files']} modules can be tested easily")
    print(f"   • Approach: Mock external dependencies, test logic and data flow")
    print(f"   • Benefits: Fast execution, no API costs, reliable CI/CD")
    
    print(f"\n🚫 Excluded from Testing (External Dependencies):")
    print(f"   • AI/LLM API calls (OpenAI, Anthropic, xAI)")
    print(f"   • Vector database operations (ChromaDB)")
    print(f"   • Web scraping (Selenium, requests)")
    print(f"   • File processing (PyPDF2, complex parsing)")
    print(f"   • Cloud services (Google Cloud, AWS)")
    
    # Test quality metrics
    test_quality_score = 0
    if total_test_functions >= 10:
        test_quality_score += 25
    if len(all_functionality) >= 5:
        test_quality_score += 25
    if len(testable_modules) > 0:
        test_quality_score += 25
    if any('mock' in tf.lower() for tf in [test_file for test_file in test_files if Path(test_file).exists()]):
        test_quality_score += 25
    
    print(f"\n🏆 Test Quality Score: {test_quality_score}/100")
    
    if test_quality_score >= 80:
        print("🎉 Excellent test coverage for dependency-free functionality!")
    elif test_quality_score >= 60:
        print("✅ Good test coverage with room for improvement")
    else:
        print("⚠️  Test coverage could be enhanced")
    
    return test_quality_score


if __name__ == "__main__":
    score = generate_coverage_report()
    exit(0 if score >= 60 else 1)
import os

for root, dirs, files in os.walk("."):
    # Ignore node_modules, .git, .svelte-kit, python cache
    dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".svelte-kit", "__pycache__", ".pytest_cache")]
    json_count = sum(1 for f in files if f.endswith(".json"))
    html_count = sum(1 for f in files if f.endswith(".html"))
    if json_count > 0 or html_count > 0:
        print(f"Path: {root} | JSON files: {json_count} | HTML files: {html_count}")

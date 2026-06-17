import urllib.request
import re

url = "https://smarter.vote/"
print(f"Fetching homepage from {url}...")
try:
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        print(f"Fetched {len(html)} characters.")
        # Search for "Showing all" or similar count patterns
        # E.g. "Showing all <span...>X</span> races" or similar
        matches = re.findall(r'Showing all.*?(\d+)\s+races', html, re.DOTALL | re.IGNORECASE)
        print("Matches for 'Showing all ... races':", matches)

        matches2 = re.findall(r'(\d+)\s+races\s+found', html, re.DOTALL | re.IGNORECASE)
        print("Matches for '... races found':", matches2)

        # Let's search for "races" with numbers around it
        matches3 = re.findall(r'(\d+)\s+races', html, re.DOTALL | re.IGNORECASE)
        print("All matches for '<number> races':", matches3[:10])

except Exception as e:
    print("Error:", e)

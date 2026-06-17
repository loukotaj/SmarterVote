import urllib.request
import xml.etree.ElementTree as ET

url = "https://smarter.vote/sitemap.xml"
print(f"Fetching sitemap from {url}...")
try:
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()
        print(f"Successfully fetched {len(xml_data)} bytes.")

        # Parse XML
        root = ET.fromstring(xml_data)

        # Namespace
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        urls = [loc.text for loc in root.findall('ns:url/ns:loc', ns)]
        print(f"Total URLs in sitemap: {len(urls)}")

        # Filter for race pages: https://smarter.vote/races/<race_id>/
        # Note the trailing slash
        race_urls = [u for u in urls if '/races/' in u and u.count('/') == 5]
        print(f"Total race URLs: {len(race_urls)}")

        # Candidate URLs: https://smarter.vote/races/<race_id>/<candidate_slug>/
        candidate_urls = [u for u in urls if '/races/' in u and u.count('/') == 6]
        print(f"Total candidate URLs: {len(candidate_urls)}")

        # Compare with MCP / DB IDs
        with open(r"C:\Users\jacob\.gemini\antigravity-ide\brain\54a9cf45-2073-4b9a-937e-bbdf393a7e87\.system_generated\steps\13\output.txt", "r") as f:
            mcp_race_ids = [line.strip() for line in f if line.strip()]

        mcp_urls = {f"https://smarter.vote/races/{rid}/" for rid in mcp_race_ids}
        sitemap_races_set = set(race_urls)

        print("In MCP but not in sitemap:", len(mcp_urls - sitemap_races_set))
        print(sorted(list(mcp_urls - sitemap_races_set)))
        print("In sitemap but not in MCP:", len(sitemap_races_set - mcp_urls))
        print(sorted(list(sitemap_races_set - mcp_urls)))

except Exception as e:
    print("Error:", e)

import os

build_races_dir = r"C:\Users\jacob\Programming\SmarterVote\SmarterVote\SmarterVote\web\build\races"
if os.path.exists(build_races_dir):
    # Find all subdirectories / files in build/races
    items = os.listdir(build_races_dir)
    print(f"Total items in build/races: {len(items)}")
    # Print the ones that don't look like index.html (or if they are folders)
    folders = [item for item in items if os.path.isdir(os.path.join(build_races_dir, item))]
    print(f"Total folders (races/slugs): {len(folders)}")
    print("Some folders:", folders[:20])
else:
    print("build/races does not exist")

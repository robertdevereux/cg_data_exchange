import os

SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".mypy_cache", ".pytest_cache",
    "migrations",  # remove this if you want migrations included
}

def combine_files(output_file="file_dump.txt"):
    all_entries = []  # list of full relative paths

    for dirpath, dirnames, filenames in os.walk("."):
        # Prune directories we don't want to descend into
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        )

        py_files = sorted(f for f in filenames if f.endswith(".py"))
        for filename in py_files:
            rel_path = os.path.join(dirpath, filename)
            # Normalise: strip leading ./
            rel_path = rel_path.lstrip("./") if rel_path.startswith("./") else rel_path
            all_entries.append(rel_path)

    with open(output_file, "w", encoding="utf-8") as out:
        for rel_path in all_entries:
            out.write(f"\n\n##### ===== {rel_path} ===== #####\n\n")
            print(f"  → {rel_path}")
            with open(rel_path, "r", encoding="utf-8") as f:
                out.write(f.read())

    print(f"\n✅ Combined {len(all_entries)} files into {output_file}")

if __name__ == "__main__":
    combine_files()

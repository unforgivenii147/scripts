# !/data/data/com.termux/files/usr/bin/python
import importlib.metadata
import logging
import sys
from pathlib import Path

# Configure clean logging to stdout
logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)]
)


def check_package_files(dist) -> list[str]:
    """Verifies that all files declared in the package installation manifest exist on disk."""
    missing_files = []

    # Locate the installation reference manifest (RECORD or files property)
    if dist.files is None:
        # Some special/editable or system packages might lack a file manifest map
        return missing_files

    for package_file in dist.files:
        # Resolve path safely using pathlib context
        file_path = Path(dist.locate_file(package_file))

        # Skip checking standard dynamic compiled cache directories (.pyc)
        if file_path.suffix == ".pyc":
            continue

        if not file_path.exists():
            missing_files.append(str(package_file))

    return missing_files


def check_package_dependencies(dist, installed_map: dict[str, str]) -> list[str]:
    """Validates if package dependency requirements are satisfied by the current environment."""
    broken_deps = []

    if dist.requires is None:
        return broken_deps

    for req_str in dist.requires:
        # Quick parse to extract package name from specifiers (e.g., "requests>=2.28.0" -> "requests")
        # Handles markers and environmental specifiers safely
        dep_name = req_str.split(";")[0].strip()

        # Strip away common operators to find the base token name
        for op in ["<", ">", "=", "!", "~"]:
            if op in dep_name:
                dep_name = dep_name.split(op)[0].strip()

        if not dep_name:
            continue

        # Normalize naming maps to lowercase to prevent matching errors
        if dep_name.lower() not in installed_map:
            broken_deps.append(req_str)

    return broken_deps


def main():
    logging.info("Starting site-packages verification scan...\n")

    # Pull metadata distributions visible globally in the active Python ecosystem
    distributions = list(importlib.metadata.distributions())

    # Map installed instances for quick lowercase lookup loops
    installed_map = {d.metadata["Name"].lower(): d.version for d in distributions}

    corrupted_packages_count = 0
    broken_deps_count = 0

    for dist in distributions:
        pkg_name = dist.metadata["Name"]
        pkg_version = dist.version

        # Attempt to track origin location path for environment context sorting
        origin_path = getattr(dist, "_path", "Unknown Environment Space")

        # Run Rule 1: Structural File Sanity Check
        missing_files = check_package_files(dist)

        # Run Rule 2: Unresolved Dependency Mismatch Check
        missing_deps = check_package_dependencies(dist, installed_map)

        # Report findings if anomalies are discovered
        if missing_files or missing_deps:
            print(f"📦 PACKAGE: {pkg_name} ({pkg_version})")
            print(f"   Location Target: {origin_path}")

            if missing_files:
                corrupted_packages_count += 1
                print(f"   ❌ Missing Files ({len(missing_files)}):")
                # Truncate output lists for scannability if a bundle is highly broken
                for f in missing_files[:5]:
                    print(f"      - {f}")
                if len(missing_files) > 5:
                    print(f"      - ... and {len(missing_files) - 5} more files missing.")

            if missing_deps:
                broken_deps_count += 1
                print(f"   ⚠️  Unresolved Dependencies:")
                for dep in missing_deps:
                    print(f"      - Missing requirement: {dep}")

            print("-" * 60)

    # Output Summary Blocks
    logging.info("=== SCAN SUMMARY ===")
    logging.info(f"Total packages evaluated: {len(distributions)}")
    logging.info(f"Packages with missing files: {corrupted_packages_count}")
    logging.info(f"Packages with missing dependencies: {broken_deps_count}")


if __name__ == "__main__":
    main()
